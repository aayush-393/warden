"""stdio transport: the agent launches Warden, Warden launches the real MCP server.

Frames are newline-delimited JSON-RPC. They are relayed byte-for-byte and observed
afterwards, so the proxy adds no parsing latency to the forwarding path. Because MCP is
bidirectional, the two pumps are fully independent: a server-initiated request (sampling,
elicitation, roots/list, ping) flows server->client while the client's request is still
outstanding, and its response flows back the other way.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from typing import Protocol

from warden.config.schema import McpStdioUpstream
from warden.logging import get_logger
from warden.mcp.correlation import Flow
from warden.mcp.observer import ConnectionObserver

# One MCP frame can be large (file contents, images). asyncio's default 64 KiB would break it.
FRAME_LIMIT = 64 * 1024 * 1024
# Shutdown ladder: close the server's stdin and wait, then SIGTERM, then SIGKILL.
STDIN_CLOSE_GRACE_S = 5.0
TERMINATE_GRACE_S = 3.0

log = get_logger("warden.mcp.stdio")


class Sink(Protocol):
    def write(self, data: bytes, /) -> None: ...
    async def drain(self) -> None: ...


async def _pump(
    reader: asyncio.StreamReader, sink: Sink, flow: Flow, obs: ConnectionObserver
) -> str:
    """Relay lines from reader to sink, handing each to the transport before observing it.

    Returns why the pump stopped, so shutdown can be attributed to the right side.
    """
    try:
        while line := await reader.readline():
            if not line.endswith(b"\n"):  # final frame without trailing newline
                line += b"\n"
            sink.write(line)
            # Observe before awaiting drain: once we yield, the peer's reply may be pumped,
            # and its request must already be on record to correlate.
            if line.strip():
                obs.observe(flow, line)
            await sink.drain()
    except (BrokenPipeError, ConnectionResetError):
        return "write_failed"  # the receiving side went away
    except ValueError:  # a line exceeded FRAME_LIMIT
        log.error("stdio.frame_too_large", flow=flow.value, limit=FRAME_LIMIT)
        return "frame_too_large"
    return "eof"


async def _log_stderr(reader: asyncio.StreamReader) -> None:
    async for line in reader:
        log.info("server.stderr", line=line.decode("utf-8", errors="replace").rstrip())


async def _reap(proc: asyncio.subprocess.Process, *, wait_s: float) -> None:
    """Make sure the server exits: wait up to `wait_s`, then SIGTERM, then SIGKILL."""
    if wait_s > 0:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), wait_s)
    if proc.returncode is None:
        log.warning("stdio.terminating_server", pid=proc.pid)
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), TERMINATE_GRACE_S)
    if proc.returncode is None:
        log.warning("stdio.killing_server", pid=proc.pid)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()


def _exit_code(proc: asyncio.subprocess.Process) -> int:
    rc = proc.returncode or 0
    return 128 - rc if rc < 0 else rc  # killed by signal N -> 128+N


async def run_stdio_proxy(
    upstream: McpStdioUpstream,
    *,
    stdin: asyncio.StreamReader,
    stdout: Sink,
    shutdown: asyncio.Event | None = None,
) -> int:
    """Run the proxy until the agent disconnects, the server exits, or `shutdown` is set.

    Returns the process exit code to use (the server's own, if it exited first).
    """
    obs = ConnectionObserver(transport="stdio", server=upstream.command)
    try:
        proc = await asyncio.create_subprocess_exec(
            upstream.command,
            *upstream.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **upstream.env},
            limit=FRAME_LIMIT,
        )
    except OSError as exc:
        log.error("stdio.spawn_failed", command=upstream.command, error=str(exc))
        return 127
    assert proc.stdin and proc.stdout and proc.stderr
    log.info("stdio.server_started", command=upstream.command, args=upstream.args, pid=proc.pid)

    c2s = asyncio.create_task(_pump(stdin, proc.stdin, Flow.CLIENT_TO_SERVER, obs))
    s2c = asyncio.create_task(_pump(proc.stdout, stdout, Flow.SERVER_TO_CLIENT, obs))
    err = asyncio.create_task(_log_stderr(proc.stderr))
    stop = asyncio.create_task((shutdown or asyncio.Event()).wait())
    try:
        done, _ = await asyncio.wait({c2s, s2c, stop}, return_when=asyncio.FIRST_COMPLETED)
        if stop in done:
            log.info("stdio.shutdown_requested")
            await _reap(proc, wait_s=0)
        else:
            for task, flow in ((c2s, Flow.CLIENT_TO_SERVER), (s2c, Flow.SERVER_TO_CLIENT)):
                if task in done:
                    log.info("stdio.stream_ended", flow=flow.value, reason=task.result())
            # Close the server's stdin and let it finish what it has in flight.
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.close()
            await _reap(proc, wait_s=STDIN_CLOSE_GRACE_S)
            # Flush whatever the server wrote before exiting.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(s2c, 2.0)
    finally:
        for task in (c2s, s2c, err, stop):
            task.cancel()
        await asyncio.gather(c2s, s2c, err, stop, return_exceptions=True)
        obs.close()
    code = _exit_code(proc)
    log.info("stdio.exit", code=code)
    return code


async def run_stdio_proxy_on_process_streams(upstream: McpStdioUpstream) -> int:
    """Bind to this process's real stdin/stdout and handle SIGINT/SIGTERM."""
    loop = asyncio.get_running_loop()

    reader = asyncio.StreamReader(limit=FRAME_LIMIT)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    transport, protocol = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(loop=loop), sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(transport, protocol, None, loop)

    shutdown = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)
    try:
        return await run_stdio_proxy(upstream, stdin=reader, stdout=writer, shutdown=shutdown)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        writer.close()

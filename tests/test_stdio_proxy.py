import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from warden.config.schema import McpStdioUpstream
from warden.mcp import stdio_proxy
from warden.mcp.stdio_proxy import FRAME_LIMIT, run_stdio_proxy

FAKE = str(Path(__file__).parent / "fakes" / "stdio_server.py")
FAKE_SERVER = McpStdioUpstream(command=sys.executable, args=[FAKE])
# Echoes every line back verbatim: lets us assert the proxy is byte-transparent.
CAT_SERVER = McpStdioUpstream(
    command=sys.executable,
    args=["-c", "import sys\nfor l in sys.stdin: sys.stdout.write(l); sys.stdout.flush()"],
)


class QueueSink:
    """Collects what the proxy writes to the agent, line by line."""

    def __init__(self) -> None:
        self.lines: asyncio.Queue[bytes] = asyncio.Queue()
        self._partial = b""

    def write(self, data: bytes) -> None:
        self._partial += data
        *whole, self._partial = self._partial.split(b"\n")
        for line in whole:
            self.lines.put_nowait(line + b"\n")

    async def drain(self) -> None:
        return None

    async def next(self) -> dict[str, Any]:
        return json.loads(await asyncio.wait_for(self.lines.get(), 10))


class Session:
    def __init__(self, upstream: McpStdioUpstream) -> None:
        self.stdin = asyncio.StreamReader(limit=FRAME_LIMIT)
        self.sink = QueueSink()
        self.shutdown = asyncio.Event()
        self.task = asyncio.create_task(
            run_stdio_proxy(upstream, stdin=self.stdin, stdout=self.sink, shutdown=self.shutdown)
        )

    def send(self, obj: dict[str, Any]) -> None:
        self.stdin.feed_data(json.dumps(obj).encode() + b"\n")

    async def finish(self) -> int:
        self.stdin.feed_eof()
        return await asyncio.wait_for(self.task, 15)


async def test_request_response_roundtrip_with_latency_logged() -> None:
    with capture_logs() as logs:
        s = Session(FAKE_SERVER)
        s.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        reply = await s.sink.next()
        assert reply["id"] == 1 and reply["result"]["protocolVersion"] == "2025-06-18"
        assert await s.finish() == 0
    responses = [e for e in logs if e["event"] == "mcp.message" and e["kind"] == "response"]
    assert responses[0]["method"] == "initialize" and responses[0]["latency_ms"] >= 0
    assert any(e["event"] == "server.stderr" and "booted" in e["line"] for e in logs)


async def test_server_initiated_request_while_client_call_outstanding() -> None:
    """Sampling: the server asks the client mid-call; the client's answer unblocks the call."""
    with capture_logs() as logs:
        s = Session(FAKE_SERVER)
        s.send({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "sample"}})
        server_req = await s.sink.next()
        assert server_req["method"] == "sampling/createMessage" and server_req["id"] == "srv-1"
        s.send({"jsonrpc": "2.0", "id": "srv-1", "result": {"role": "assistant"}})
        final = await s.sink.next()
        assert final["id"] == 7 and final["result"]["sampled"] == {"role": "assistant"}
        await s.finish()
    answered = [e for e in logs if e["event"] == "mcp.message" and e.get("id") == "srv-1"]
    assert [e["kind"] for e in answered] == ["request", "response"]
    assert answered[1]["method"] == "sampling/createMessage"  # correlated to the server's request
    assert not any(e.get("unmatched") for e in logs)


async def test_cancellation_notification_is_relayed_and_retires_request() -> None:
    with capture_logs() as logs:
        s = Session(FAKE_SERVER)
        s.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "hang"}})
        s.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 3}})
        seen = await s.sink.next()
        assert seen["method"] == "notifications/saw_cancel" and seen["params"]["requestId"] == 3
        await s.finish()
    cancel = [e for e in logs if e.get("cancelled_method")]
    assert cancel and cancel[0]["cancelled_method"] == "tools/call"
    assert not any(e["event"] == "mcp.pending_at_close" for e in logs)


async def test_relay_is_byte_exact_including_odd_and_invalid_frames() -> None:
    frames = [
        b'{"jsonrpc":"2.0",  "id": 1,"method":"ping"  }',  # unusual whitespace
        b'{"id":2,"method":"x","params":{"s":"\\u00e9\\ud83d\\ude00"}}',  # escapes preserved
        b"this is not json",  # forwarded anyway; logged as unparseable
        b'{"jsonrpc":"2.0","id":3,"result":{}}',
    ]
    with capture_logs() as logs:
        s = Session(CAT_SERVER)
        for f in frames:
            s.stdin.feed_data(f + b"\n")
        echoed = [await asyncio.wait_for(s.sink.lines.get(), 10) for _ in frames]
        await s.finish()
    assert echoed == [f + b"\n" for f in frames]
    assert any(e["event"] == "mcp.unparseable" for e in logs)


async def test_large_frame_over_default_stream_limit() -> None:
    big = json.dumps({"id": 1, "result": {"blob": "x" * (2 * 1024 * 1024)}}).encode()
    s = Session(CAT_SERVER)
    s.stdin.feed_data(big + b"\n")
    assert await asyncio.wait_for(s.sink.lines.get(), 20) == big + b"\n"
    await s.finish()


async def test_agent_eof_closes_server_and_exits_cleanly() -> None:
    s = Session(FAKE_SERVER)
    assert await s.finish() == 0


async def test_server_exit_code_is_propagated() -> None:
    s = Session(McpStdioUpstream(command=sys.executable, args=["-c", "import sys; sys.exit(3)"]))
    assert await asyncio.wait_for(s.task, 15) == 3


async def test_spawn_failure_returns_127() -> None:
    s = Session(McpStdioUpstream(command="/nonexistent/warden-test-binary"))
    assert await asyncio.wait_for(s.task, 5) == 127


async def test_shutdown_terminates_a_hung_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stdio_proxy, "TERMINATE_GRACE_S", 2.0)
    s = Session(
        McpStdioUpstream(command=sys.executable, args=["-c", "import time; time.sleep(60)"])
    )
    await asyncio.sleep(0.3)
    s.shutdown.set()
    code = await asyncio.wait_for(s.task, 10)
    assert code == 128 + 15  # SIGTERM


async def test_end_to_end_through_the_cli(tmp_path: Path) -> None:
    """Real process boundaries: stdout carries only protocol; logs go to stderr and the file."""
    log_file = tmp_path / "warden.log"
    cfg = tmp_path / "warden.yaml"
    cfg.write_text(
        f"""
listeners: [{{type: stdio}}]
upstreams:
  fake: {{kind: mcp_stdio, command: {sys.executable}, args: ["{FAKE}"]}}
policy: {{address: "localhost:1"}}
observability: {{log_file: {log_file}}}
"""
    )
    pipe = asyncio.subprocess.PIPE
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        *("-m", "warden", "run", "-c", str(cfg)),
        stdin=pipe,
        stdout=pipe,
        stderr=pipe,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    proc.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"tools/call",')
    proc.stdin.write(b'"params":{"name":"echo","arguments":{"t":"hi"}}}\n')
    await proc.stdin.drain()
    line = await asyncio.wait_for(proc.stdout.readline(), 15)
    assert json.loads(line)["result"]["content"][0]["text"] == "hi"
    proc.stdin.close()
    out, err = await asyncio.wait_for(asyncio.gather(proc.stdout.read(), proc.stderr.read()), 15)
    assert await asyncio.wait_for(proc.wait(), 15) == 0
    assert out == b""  # nothing but protocol frames on stdout
    events = [json.loads(ln)["event"] for ln in err.splitlines()]
    assert "mcp.message" in events and "server.stderr" in events
    assert (
        '"event": "mcp.message"' in log_file.read_text()
        or '"event":"mcp.message"' in log_file.read_text()
    )


async def test_shutdown_kills_a_server_that_ignores_sigterm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the shutdown path used to stop at SIGTERM and leave such servers running."""
    monkeypatch.setattr(stdio_proxy, "TERMINATE_GRACE_S", 0.5)
    stubborn = (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('ready', flush=True)\n"
        "time.sleep(60)\n"
    )
    s = Session(McpStdioUpstream(command=sys.executable, args=["-c", stubborn]))
    assert await asyncio.wait_for(s.sink.lines.get(), 10) == b"ready\n"  # handler installed
    s.shutdown.set()
    assert await asyncio.wait_for(s.task, 10) == 128 + 9  # SIGKILL


async def test_stream_end_is_attributed_to_the_side_that_ended() -> None:
    with capture_logs() as logs:
        s = Session(
            McpStdioUpstream(command=sys.executable, args=["-c", "import sys; sys.exit(0)"])
        )
        await asyncio.wait_for(s.task, 15)
    ended = [e for e in logs if e["event"] == "stdio.stream_ended"]
    assert ended and ended[0]["flow"] == "server_to_client" and ended[0]["reason"] == "eof"

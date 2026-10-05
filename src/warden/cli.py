"""`warden` command line: run the proxy from a YAML config, or just validate one."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from warden.config import WardenConfig, load_config
from warden.config.schema import (
    HttpListener,
    McpHttpUpstream,
    McpStdioUpstream,
    StdioListener,
)
from warden.logging import configure_logging, get_logger
from warden.mcp.http_proxy import serve_http_proxy
from warden.mcp.stdio_proxy import run_stdio_proxy_on_process_streams


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warden", description="Policy firewall for agent traffic."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("run", "start the proxy"), ("validate", "check a config file")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("-c", "--config", type=Path, required=True, help="path to warden.yaml")
    return parser


async def _run(config: WardenConfig) -> int:
    log = get_logger("warden")
    log.info("warden.start", mode=config.mode.value, listeners=len(config.listeners))
    tasks: list[asyncio.Task[object]] = []
    for listener in config.listeners:
        upstream = config.upstreams[config.upstream_name(listener)]
        if isinstance(listener, StdioListener) and isinstance(upstream, McpStdioUpstream):
            # stdio owns the process; validation guarantees it is the only listener.
            return await run_stdio_proxy_on_process_streams(upstream)
        if isinstance(listener, HttpListener) and isinstance(upstream, McpHttpUpstream):
            tasks.append(asyncio.create_task(serve_http_proxy(listener, upstream)))
        else:
            log.error("warden.unsupported_listener", listener=listener.type)
            return 2
    await asyncio.gather(*tasks)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except (ValidationError, OSError, ValueError) as exc:
        print(f"warden: invalid config {args.config}:\n{exc}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(f"{args.config}: ok", file=sys.stderr)
        return 0

    obs = config.observability
    try:
        configure_logging(obs.log_level, obs.log_file)
    except OSError as exc:
        print(f"warden: cannot open log file {obs.log_file}: {exc}", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_run(config))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

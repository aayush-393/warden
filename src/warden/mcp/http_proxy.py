"""Streamable HTTP transport: a reverse proxy for a single MCP endpoint.

Per the MCP spec the endpoint takes POST (client->server messages; the reply is JSON or an
SSE stream), GET (a standalone SSE stream for server-initiated messages) and DELETE (end
session), and uses the `Mcp-Session-Id` header. Bodies are streamed through chunk by chunk,
never buffered, so SSE keeps its latency. An SSE parser watches the same bytes to log and
correlate the JSON-RPC messages inside, including server->client requests.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import AsyncGenerator, AsyncIterator, Iterable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from warden.config.schema import HttpListener, McpHttpUpstream
from warden.logging import get_logger
from warden.mcp.correlation import Flow
from warden.mcp.observer import ConnectionObserver
from warden.mcp.sse import SseParser

SESSION_HEADER = "mcp-session-id"
MAX_SESSIONS = 1024
# Observing a non-streamed JSON reply means buffering a copy; skip observation past this size.
MAX_OBSERVED_JSON_BYTES = 8 * 1024 * 1024
NO_BODY_STATUSES = frozenset({202, 204, 304})

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
# We ask upstream for identity encoding so the observer sees plain bytes, and let the
# ASGI server frame the body, hence no accept-encoding / content-length / content-encoding.
_STRIP_REQUEST = _HOP_BY_HOP | {"host", "content-length", "accept-encoding"}
_STRIP_RESPONSE = _HOP_BY_HOP | {"content-length", "content-encoding"}

log = get_logger("warden.mcp.http")


class _Sessions:
    """Observers by MCP session id, bounded so abandoned sessions can't leak."""

    def __init__(self, limit: int = MAX_SESSIONS) -> None:
        self._limit = limit
        self._by_id: OrderedDict[str, ConnectionObserver] = OrderedDict()

    def get(self, session_id: str) -> ConnectionObserver | None:
        obs = self._by_id.get(session_id)
        if obs is not None:
            self._by_id.move_to_end(session_id)
        return obs

    def add(self, session_id: str, obs: ConnectionObserver) -> None:
        self._by_id[session_id] = obs
        if len(self._by_id) > self._limit:
            _, evicted = self._by_id.popitem(last=False)
            evicted.close()

    def drop(self, session_id: str) -> None:
        obs = self._by_id.pop(session_id, None)
        if obs is not None:
            obs.close()


def _forward_headers(
    headers: Iterable[tuple[str, str]], strip: frozenset[str]
) -> list[tuple[str, str]]:
    return [(k, v) for k, v in headers if k.lower() not in strip]


def _origin_allowed(origin: str | None, allowed_hosts: frozenset[str]) -> bool:
    """Reject browser cross-origin requests (DNS-rebinding defence, required by the MCP spec)."""
    if origin is None:
        return True  # non-browser client
    return (urlsplit(origin).hostname or "") in allowed_hosts


def create_app(
    upstream_url: str,
    *,
    listen_host: str = "127.0.0.1",
    allowed_origins: Iterable[str] = (),
    client: httpx.AsyncClient | None = None,
) -> Starlette:
    """Build the proxy app. `client` is injectable for tests."""
    endpoint_path = urlsplit(upstream_url).path or "/"
    allowed_hosts = frozenset(
        {"localhost", "127.0.0.1", "::1", listen_host}
        | {urlsplit(o).hostname or o for o in allowed_origins}
    )
    sessions = _Sessions()
    owned_client = client is None
    http = client or httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10, read=None, write=30, pool=10),
        follow_redirects=False,
    )

    async def handle(request: Request) -> Response:
        if not _origin_allowed(request.headers.get("origin"), allowed_hosts):
            log.warning("http.origin_rejected", origin=request.headers.get("origin"))
            return JSONResponse({"error": "origin not allowed"}, status_code=403)

        session_id = request.headers.get(SESSION_HEADER)
        obs = sessions.get(session_id) if session_id else None
        if obs is None:
            obs = ConnectionObserver(transport="http", session=session_id)
            if session_id:
                sessions.add(session_id, obs)

        body = await request.body() if request.method == "POST" else b""
        if body:
            obs.observe(Flow.CLIENT_TO_SERVER, body)

        upstream_req = http.build_request(
            request.method,
            upstream_url,
            headers=[
                *_forward_headers(
                    ((k.decode("latin-1"), v.decode("latin-1")) for k, v in request.headers.raw),
                    _STRIP_REQUEST,
                ),
                ("accept-encoding", "identity"),
            ],
            content=body or None,
        )
        try:
            upstream = await http.send(upstream_req, stream=True)
        except httpx.HTTPError as exc:
            log.error("http.upstream_error", error=repr(exc), method=request.method)
            return JSONResponse({"error": "upstream unavailable"}, status_code=502)

        new_session = upstream.headers.get(SESSION_HEADER)
        if new_session and not session_id:
            obs.bind(session=new_session)
            sessions.add(new_session, obs)
        if session_id and (
            (request.method == "DELETE" and upstream.status_code < 300)
            or upstream.status_code == 404
        ):
            sessions.drop(session_id)  # ended, or the server no longer knows it

        headers = _forward_headers(upstream.headers.multi_items(), _STRIP_RESPONSE)
        if upstream.status_code in NO_BODY_STATUSES or request.method == "DELETE":
            await upstream.aclose()
            response: Response = Response(status_code=upstream.status_code)
        else:
            response = StreamingResponse(_relay(upstream, obs), status_code=upstream.status_code)
        response.raw_headers = [
            (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers
        ]
        return response

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncGenerator[None]:
        yield
        if owned_client:
            await http.aclose()

    return Starlette(
        routes=[Route(endpoint_path, handle, methods=["GET", "POST", "DELETE"])],
        lifespan=lifespan,
    )


async def _relay(upstream: httpx.Response, obs: ConnectionObserver) -> AsyncIterator[bytes]:
    """Stream the upstream body to the agent, observing a copy without delaying it."""
    ctype = upstream.headers.get("content-type", "").split(";")[0].strip().lower()
    sse = SseParser() if ctype == "text/event-stream" else None
    buf = bytearray() if ctype == "application/json" else None
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
            if sse is not None:
                for event in sse.feed(chunk):
                    # Empty data = priming/keep-alive event; other event types aren't JSON-RPC.
                    if event.data and event.event in (None, "message"):
                        obs.observe(Flow.SERVER_TO_CLIENT, event.data)
            elif buf is not None and len(buf) <= MAX_OBSERVED_JSON_BYTES:
                buf.extend(chunk)
        if buf and len(buf) <= MAX_OBSERVED_JSON_BYTES:
            obs.observe(Flow.SERVER_TO_CLIENT, bytes(buf))
    except httpx.HTTPError as exc:
        # Upstream dropped mid-body. Re-raise so the ASGI server aborts the connection: ending
        # the stream normally would present a truncated body to the agent as a complete one.
        log.warning("http.upstream_stream_error", error=repr(exc))
        raise
    finally:
        await upstream.aclose()


async def serve_http_proxy(listener: HttpListener, upstream: McpHttpUpstream) -> None:
    app = create_app(
        upstream.url, listen_host=listener.host, allowed_origins=listener.allowed_origins
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app, host=listener.host, port=listener.port, log_config=None, access_log=False
        )
    )
    log.info(
        "http.listening",
        host=listener.host,
        port=listener.port,
        endpoint=urlsplit(upstream.url).path or "/",
        upstream=upstream.url,
    )
    await server.serve()


__all__ = ["create_app", "serve_http_proxy"]

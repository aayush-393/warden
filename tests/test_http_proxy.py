import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from structlog.testing import capture_logs

from warden.mcp.http_proxy import create_app

UPSTREAM_URL = "http://upstream.test/mcp"


def sse(*events: dict[str, Any]) -> bytes:
    return b"".join(
        b"id: %d\ndata: %s\n\n" % (i, json.dumps(e).encode()) for i, e in enumerate(events, 1)
    )


class FakeUpstream:
    """Scripted streamable-HTTP MCP server; records what the proxy sent it."""

    def __init__(self) -> None:
        self.seen: list[Request] = []
        self.app = Starlette(routes=[Route("/mcp", self.handle, methods=["GET", "POST", "DELETE"])])

    async def handle(self, request: Request) -> Response:
        self.seen.append(request)
        if request.method == "DELETE":
            return Response(status_code=200)
        if request.method == "GET":
            note: dict[str, Any] = {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {},
            }
            return Response(sse(note), media_type="text/event-stream")
        msg = json.loads(await request.body())
        method = msg.get("method")
        if method == "initialize":
            return JSONResponse(
                {"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18"}},
                headers={"Mcp-Session-Id": "sess-1"},
            )
        if method == "tools/call":  # SSE reply containing a server->client request, then the result
            events: list[dict[str, Any]] = [
                {"jsonrpc": "2.0", "id": 99, "method": "elicitation/create", "params": {}},
                {"jsonrpc": "2.0", "id": msg["id"], "result": {"ok": True}},
            ]
            return Response(sse(*events), media_type="text/event-stream")
        if method is None:  # a client *response* to a server request
            return Response(status_code=202)
        if "id" not in msg:
            return Response(status_code=202)
        return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "result": {}})


@asynccontextmanager
async def proxy_client(upstream: FakeUpstream, **kwargs: Any) -> AsyncGenerator[httpx.AsyncClient]:
    upstream_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream.app), base_url="http://upstream.test"
    )
    app = create_app(UPSTREAM_URL, client=upstream_client, **kwargs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        yield client
    await upstream_client.aclose()


def rpc(method: str, id: int | None = None, **params: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
    if id is not None:
        msg["id"] = id
    return msg


HEADERS = {"Accept": "application/json, text/event-stream"}


async def test_initialize_returns_session_id_and_json_body() -> None:
    up = FakeUpstream()
    async with proxy_client(up) as client:
        r = await client.post("/mcp", json=rpc("initialize", 1), headers=HEADERS)
    assert r.status_code == 200
    assert r.headers["mcp-session-id"] == "sess-1"
    assert r.json()["result"]["protocolVersion"] == "2025-06-18"


async def test_request_headers_are_forwarded_except_hop_by_hop() -> None:
    up = FakeUpstream()
    async with proxy_client(up) as client:
        await client.post(
            "/mcp",
            json=rpc("ping", 1),
            headers={
                **HEADERS,
                "Mcp-Session-Id": "sess-1",
                "MCP-Protocol-Version": "2025-06-18",
                "Authorization": "Bearer t0k",
                "Last-Event-ID": "4",
                "Connection": "keep-alive, X-Drop",
                "Accept-Encoding": "gzip",
            },
        )
    sent = up.seen[0].headers
    assert sent["mcp-session-id"] == "sess-1"
    assert sent["mcp-protocol-version"] == "2025-06-18"
    assert sent["authorization"] == "Bearer t0k"
    assert sent["last-event-id"] == "4"
    assert sent["host"] == "upstream.test"  # rewritten to the upstream, not the proxy's host
    assert sent["accept-encoding"] == "identity"


async def test_notification_gets_202_with_empty_body() -> None:
    up = FakeUpstream()
    async with proxy_client(up) as client:
        r = await client.post("/mcp", json=rpc("notifications/initialized"), headers=HEADERS)
    assert r.status_code == 202 and r.content == b""


async def test_sse_reply_with_server_request_is_relayed_and_correlated() -> None:
    up = FakeUpstream()
    with capture_logs() as logs:
        async with proxy_client(up) as client:
            h = {**HEADERS, "Mcp-Session-Id": "sess-1"}
            r = await client.post("/mcp", json=rpc("tools/call", 5, name="x"), headers=h)
            assert r.headers["content-type"].startswith("text/event-stream")
            assert b"elicitation/create" in r.content and b'"ok": true' in r.content
            # The agent answers the server's elicitation request with a separate POST.
            answer = {"jsonrpc": "2.0", "id": 99, "result": {"action": "accept"}}
            r2 = await client.post("/mcp", json=answer, headers=h)
            assert r2.status_code == 202
    msgs = [e for e in logs if e["event"] == "mcp.message"]
    elicit = [e for e in msgs if e["id"] == 99]
    assert [e["kind"] for e in elicit] == ["request", "response"]
    assert elicit[1]["method"] == "elicitation/create" and "latency_ms" in elicit[1]
    call = [e for e in msgs if e["id"] == 5]
    assert call[1]["method"] == "tools/call"
    assert not any(e.get("unmatched") for e in msgs)


async def test_session_is_learned_from_initialize_and_shared_across_requests() -> None:
    """Initialize has no session header; follow-ups carry one and must reach the same observer."""
    up = FakeUpstream()
    with capture_logs() as logs:
        async with proxy_client(up) as client:
            await client.post("/mcp", json=rpc("initialize", 1), headers=HEADERS)
            h = {**HEADERS, "Mcp-Session-Id": "sess-1"}
            await client.post("/mcp", json=rpc("tools/call", 2, name="x"), headers=h)
            await client.post("/mcp", json={"jsonrpc": "2.0", "id": 99, "result": {}}, headers=h)
    answered = [e for e in logs if e["event"] == "mcp.message" and e["id"] == 99]
    assert (
        answered[-1].get("unmatched") is not True and answered[-1]["method"] == "elicitation/create"
    )


async def test_get_opens_server_initiated_stream() -> None:
    up = FakeUpstream()
    async with proxy_client(up) as client:
        r = await client.get("/mcp", headers={"Accept": "text/event-stream", "Mcp-Session-Id": "s"})
    assert r.headers["content-type"].startswith("text/event-stream")
    assert b"notifications/message" in r.content


async def test_delete_ends_session_and_drops_observer() -> None:
    up = FakeUpstream()
    with capture_logs() as logs:
        async with proxy_client(up) as client:
            await client.post("/mcp", json=rpc("initialize", 1), headers=HEADERS)
            r = await client.delete("/mcp", headers={"Mcp-Session-Id": "sess-1"})
    assert r.status_code == 200
    assert any(e["event"] == "mcp.connection_closed" for e in logs)


async def test_foreign_origin_is_rejected_but_localhost_allowed() -> None:
    up = FakeUpstream()
    async with proxy_client(up) as client:
        bad = await client.post(
            "/mcp", json=rpc("ping", 1), headers={**HEADERS, "Origin": "https://evil.example"}
        )
        ok = await client.post(
            "/mcp", json=rpc("ping", 1), headers={**HEADERS, "Origin": "http://localhost:5173"}
        )
    assert bad.status_code == 403 and ok.status_code == 200
    assert len(up.seen) == 1  # the rejected request never reached upstream


async def test_other_paths_are_not_proxied() -> None:
    async with proxy_client(FakeUpstream()) as client:
        assert (await client.get("/.well-known/oauth-authorization-server")).status_code == 404


async def test_upstream_down_gives_502() -> None:
    dead = httpx.AsyncClient(transport=httpx.MockTransport(_refuse))
    app = create_app(UPSTREAM_URL, client=dead)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        r = await client.post("/mcp", json=rpc("ping", 1), headers=HEADERS)
    assert r.status_code == 502


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


# --- real sockets: prove SSE is streamed, not buffered ---------------------------------


@asynccontextmanager
async def serve(app: Starlette) -> AsyncGenerator[str]:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def test_sse_events_arrive_before_upstream_finishes() -> None:
    release = asyncio.Event()

    async def slow_stream(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            yield sse({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"n": 1}})
            await release.wait()  # upstream is still mid-response
            yield sse({"jsonrpc": "2.0", "id": 1, "result": {}})

        return StreamingResponse(gen(), media_type="text/event-stream")

    upstream_app = Starlette(routes=[Route("/mcp", slow_stream, methods=["POST"])])
    async with serve(upstream_app) as upstream_url:
        proxy = create_app(f"{upstream_url}/mcp")
        async with (
            serve(proxy) as proxy_url,
            httpx.AsyncClient() as client,
            client.stream(
                "POST", f"{proxy_url}/mcp", json=rpc("tools/call", 1), headers=HEADERS
            ) as r,
        ):
            chunks = r.aiter_bytes()
            first = await asyncio.wait_for(anext(chunks), 5)  # would hang if buffered
            assert b"notifications/progress" in first
            release.set()
            rest = b"".join([c async for c in chunks])
            assert b'"result"' in rest


# --- resumption, standalone stream, cancellation, disconnects, failures -------------------


class StreamingUpstream:
    """Upstream with long-lived streams whose lifecycle the test controls."""

    def __init__(self) -> None:
        self.seen_last_event_ids: list[str | None] = []
        self.cancel_seen = asyncio.Event()
        self.stream_closed = asyncio.Event()
        self.app = Starlette(routes=[Route("/mcp", self.handle, methods=["GET", "POST"])])

    async def handle(self, request: Request) -> Response:
        if request.method == "GET":
            return await self._get(request)
        msg = json.loads(await request.body())
        method = msg.get("method")
        if method == "notifications/cancelled":
            self.cancel_seen.set()
            return Response(status_code=202)
        if method is None:  # client answering a server request
            return Response(status_code=202)
        if method == "tools/call":
            name = msg["params"]["name"]
            if name == "slow":  # open stream that ends (without a result) once cancelled
                return StreamingResponse(self._until_cancelled(), media_type="text/event-stream")
            if name == "endless":  # open stream; records when the proxy closes it
                return StreamingResponse(self._endless(), media_type="text/event-stream")
            if name == "dies":  # one event, then the connection is torn down
                return StreamingResponse(self._dies(), media_type="text/event-stream")
        return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "result": {}})

    async def _get(self, request: Request) -> Response:
        last = request.headers.get("last-event-id")
        self.seen_last_event_ids.append(last)
        if last is None:  # fresh stream: the server asks the client something
            req: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": 77,
                "method": "sampling/createMessage",
                "params": {},
            }
            return Response(sse(req), media_type="text/event-stream")
        # resumption: replay what the client missed, with the original event ids
        body = b"id: 5\ndata: " + json.dumps({"jsonrpc": "2.0", "method": "n/5"}).encode() + b"\n\n"
        return Response(body, media_type="text/event-stream")

    async def _until_cancelled(self) -> AsyncIterator[bytes]:
        yield b": open\n\n"
        await self.cancel_seen.wait()

    async def _endless(self) -> AsyncIterator[bytes]:
        try:
            while True:
                yield sse({"jsonrpc": "2.0", "method": "notifications/tick", "params": {}})
                await asyncio.sleep(0.02)
        finally:
            self.stream_closed.set()

    async def _dies(self) -> AsyncIterator[bytes]:
        yield sse({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}})
        await asyncio.sleep(0.05)
        raise RuntimeError("upstream crashed")


@asynccontextmanager
async def real_proxy(up: StreamingUpstream) -> AsyncGenerator[tuple[str, httpx.AsyncClient]]:
    async with (
        serve(up.app) as upstream_url,
        serve(create_app(f"{upstream_url}/mcp")) as proxy_url,
        httpx.AsyncClient(base_url=proxy_url, timeout=10) as client,
    ):
        yield proxy_url, client


async def test_standalone_get_stream_carries_server_request_and_answer_correlates() -> None:
    up = StreamingUpstream()
    with capture_logs() as logs:
        async with real_proxy(up) as (_, client):
            h = {"Mcp-Session-Id": "s1"}
            r = await client.get("/mcp", headers={**h, "Accept": "text/event-stream"})
            assert b"sampling/createMessage" in r.content
            answer = {"jsonrpc": "2.0", "id": 77, "result": {"role": "assistant"}}
            assert (await client.post("/mcp", json=answer, headers=h)).status_code == 202
    sampled = [e for e in logs if e["event"] == "mcp.message" and e["id"] == 77]
    assert [e["kind"] for e in sampled] == ["request", "response"]
    assert sampled[1]["method"] == "sampling/createMessage"


async def test_last_event_id_is_forwarded_and_sse_ids_pass_through_exactly() -> None:
    up = StreamingUpstream()
    async with real_proxy(up) as (_, client):
        r = await client.get(
            "/mcp",
            headers={"Accept": "text/event-stream", "Last-Event-ID": "4", "Mcp-Session-Id": "s"},
        )
    assert up.seen_last_event_ids == ["4"]
    assert r.content.startswith(b"id: 5\ndata: ")  # event id preserved byte for byte


async def test_cancellation_over_http_retires_the_request_and_ends_the_stream() -> None:
    up = StreamingUpstream()
    with capture_logs() as logs:
        async with real_proxy(up) as (_, client):
            h = {**HEADERS, "Mcp-Session-Id": "s1"}

            async def call() -> bytes:
                r = await client.post("/mcp", json=rpc("tools/call", 5, name="slow"), headers=h)
                return r.content

            pending = asyncio.create_task(call())
            await asyncio.sleep(0.2)  # the tools/call stream is open and unanswered
            cancel = rpc("notifications/cancelled", requestId=5)
            assert (await client.post("/mcp", json=cancel, headers=h)).status_code == 202
            await asyncio.wait_for(pending, 5)  # stream ends once upstream honours the cancel
    cancelled = [e for e in logs if e.get("cancelled_method")]
    assert cancelled and cancelled[0]["cancelled_method"] == "tools/call"


async def test_agent_disconnect_closes_the_upstream_stream() -> None:
    up = StreamingUpstream()
    async with real_proxy(up) as (_, client):
        async with client.stream(
            "POST", "/mcp", json=rpc("tools/call", 1, name="endless"), headers=HEADERS
        ) as r:
            await anext(r.aiter_bytes())  # got the first event, then the agent walks away
        await asyncio.wait_for(up.stream_closed.wait(), 5)  # proxy released the upstream stream


async def test_upstream_dying_mid_stream_is_surfaced_and_proxy_survives() -> None:
    up = StreamingUpstream()
    with capture_logs() as logs:
        async with real_proxy(up) as (_, client):
            with pytest.raises(httpx.HTTPError):
                r = await client.post(
                    "/mcp", json=rpc("tools/call", 1, name="dies"), headers=HEADERS
                )
                r.raise_for_status()
                _ = r.content  # truncated body must not look like a clean, complete reply
            ok = await client.post("/mcp", json=rpc("ping", 2), headers=HEADERS)
            assert ok.status_code == 200  # one bad stream doesn't take the proxy down
    assert any(e["event"] == "http.upstream_stream_error" for e in logs)


async def test_expired_session_404_drops_observer() -> None:
    expired = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "no session"}))
    )
    app = create_app(UPSTREAM_URL, client=expired)
    with capture_logs() as logs:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            r = await client.post(
                "/mcp", json=rpc("ping", 1), headers={**HEADERS, "Mcp-Session-Id": "gone"}
            )
    assert r.status_code == 404  # passed through so the client knows to re-initialize
    assert any(e["event"] == "mcp.connection_closed" for e in logs)


def test_session_registry_is_bounded() -> None:
    from warden.mcp.http_proxy import _Sessions  # pyright: ignore[reportPrivateUsage]
    from warden.mcp.observer import ConnectionObserver

    sessions = _Sessions(limit=2)
    for sid in ("a", "b", "c"):
        sessions.add(sid, ConnectionObserver())
    assert sessions.get("a") is None and sessions.get("c") is not None

"""Request/response correlation for a bidirectional MCP connection.

MCP is symmetric: either side may send requests. The two directions use independent
id spaces, so each gets its own pending table. Cancellation notifications refer to
requests the *sender* previously issued, which lets us retire entries from the right table.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum

from warden.mcp.jsonrpc import IdKey, Kind, Message, as_dict, id_key

CANCELLED_METHOD = "notifications/cancelled"
# Bound on outstanding requests per direction, so a peer that never answers can't grow memory.
MAX_PENDING = 4096


class Flow(StrEnum):
    """Which way a frame travels through the proxy."""

    CLIENT_TO_SERVER = "client_to_server"
    SERVER_TO_CLIENT = "server_to_client"


@dataclass(frozen=True, slots=True)
class Pending:
    method: str
    started: float  # time.monotonic()


@dataclass(frozen=True, slots=True)
class Observation:
    flow: Flow
    message: Message
    # For responses/errors: the request they answer.
    request_method: str | None = None
    latency_s: float | None = None
    # A response with no known request (never seen, cancelled, or evicted).
    unmatched: bool = False
    # For cancellations: the request being cancelled, and how long it was outstanding.
    cancelled_method: str | None = None


class Correlator:
    def __init__(self, max_pending: int = MAX_PENDING) -> None:
        self._max = max_pending
        # Requests sent by the client, awaiting a server response (and vice versa).
        self._pending: dict[Flow, OrderedDict[IdKey, Pending]] = {
            Flow.CLIENT_TO_SERVER: OrderedDict(),
            Flow.SERVER_TO_CLIENT: OrderedDict(),
        }

    def pending_count(self, flow: Flow | None = None) -> int:
        if flow is not None:
            return len(self._pending[flow])
        return sum(len(t) for t in self._pending.values())

    def observe(self, flow: Flow, msg: Message) -> Observation:
        # A request travelling client->server is answered by a response travelling
        # server->client, so responses look up the table of the *opposite* flow.
        if msg.kind is Kind.REQUEST and msg.id_key is not None and msg.method is not None:
            table = self._pending[flow]
            table[msg.id_key] = Pending(msg.method, time.monotonic())
            if len(table) > self._max:
                table.popitem(last=False)
            return Observation(flow, msg)

        if msg.kind in (Kind.RESPONSE, Kind.ERROR) and msg.id_key is not None:
            entry = self._pending[_opposite(flow)].pop(msg.id_key, None)
            if entry is None:
                return Observation(flow, msg, unmatched=True)
            return Observation(
                flow,
                msg,
                request_method=entry.method,
                latency_s=time.monotonic() - entry.started,
            )

        if msg.kind is Kind.NOTIFICATION and msg.method == CANCELLED_METHOD:
            return self._observe_cancel(flow, msg)

        return Observation(flow, msg)

    def _observe_cancel(self, flow: Flow, msg: Message) -> Observation:
        request_id = (as_dict(msg.params) or {}).get("requestId")
        if isinstance(request_id, str | int) and not isinstance(request_id, bool):
            # The sender cancels a request it issued earlier, so use its own table.
            entry = self._pending[flow].pop(id_key(request_id), None)
            if entry is not None:
                return Observation(flow, msg, cancelled_method=entry.method)
        return Observation(flow, msg)


def _opposite(flow: Flow) -> Flow:
    if flow is Flow.CLIENT_TO_SERVER:
        return Flow.SERVER_TO_CLIENT
    return Flow.CLIENT_TO_SERVER

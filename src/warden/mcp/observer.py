"""Observes proxied frames: parses, correlates, and logs. Never touches the wire."""

from __future__ import annotations

from typing import Any

from warden.logging import get_logger
from warden.mcp.correlation import Correlator, Flow, Observation
from warden.mcp.jsonrpc import parse


class ConnectionObserver:
    """One per MCP connection (a stdio process, or an HTTP session)."""

    def __init__(self, **context: Any) -> None:
        self.correlator = Correlator()
        self._log = get_logger("warden.mcp").bind(**context)

    def bind(self, **context: Any) -> None:
        self._log = self._log.bind(**context)

    def observe(self, flow: Flow, raw: bytes | str) -> None:
        """Inspect one frame. Errors are logged, never raised: observation must not break relay."""
        try:
            messages = parse(raw)
        except ValueError:
            self._log.warning("mcp.unparseable", flow=flow.value, bytes=len(raw))
            return
        try:
            for msg in messages:
                self._log_observation(self.correlator.observe(flow, msg), len(raw))
        except Exception:
            self._log.exception("mcp.observe_failed", flow=flow.value)

    def _log_observation(self, obs: Observation, size: int) -> None:
        msg = obs.message
        fields: dict[str, Any] = {
            "flow": obs.flow.value,
            "kind": msg.kind.value,
            "id": msg.id,
            "method": msg.method or obs.request_method,
            "bytes": size,
        }
        if obs.latency_s is not None:
            fields["latency_ms"] = round(obs.latency_s * 1000, 2)
        if obs.unmatched:
            fields["unmatched"] = True
        if msg.error_code is not None:
            fields["error_code"] = msg.error_code
        if obs.cancelled_method is not None:
            fields["cancelled_method"] = obs.cancelled_method
        self._log.info("mcp.message", **fields)
        self._log.debug("mcp.payload", id=msg.id, flow=obs.flow.value, payload=msg.body)

    def close(self) -> None:
        pending = self.correlator.pending_count()
        if pending:
            self._log.warning("mcp.pending_at_close", count=pending)
        self._log.info("mcp.connection_closed")

import pytest
from pydantic import ValidationError

from warden.model import (
    Action,
    Actor,
    Decision,
    Direction,
    Event,
    Protocol,
    Resource,
    ResourceKind,
    SessionContext,
    Verdict,
)


def make_event(**overrides: object) -> Event:
    base = {
        "direction": Direction.REQUEST,
        "protocol": Protocol.MCP,
        "actor": Actor(agent_id="agent-1"),
        "action": Action.CALL_TOOL,
        "resource": Resource(kind=ResourceKind.TOOL, server="fs", name="read_file"),
        "payload": {"path": "/tmp/x"},
        "session": SessionContext(session_id="s1"),
    }
    return Event.model_validate({**base, **overrides})


def test_event_defaults_and_roundtrip() -> None:
    ev = make_event()
    assert ev.event_id
    assert ev.session.taint_labels == frozenset()
    assert Event.model_validate_json(ev.model_dump_json()) == ev


def test_event_is_frozen() -> None:
    with pytest.raises(ValidationError):
        make_event().event_id = "other"  # type: ignore[misc]


def test_event_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        make_event(bogus=1)


def test_modify_requires_patch() -> None:
    with pytest.raises(ValidationError):
        Decision(verdict=Verdict.MODIFY, reason="redact")
    d = Decision.modify({"path": "[REDACTED]"}, "redact", rule_id="pii-1")
    assert d.patched_payload == {"path": "[REDACTED]"}


def test_patch_forbidden_on_other_verdicts() -> None:
    with pytest.raises(ValidationError):
        Decision(verdict=Verdict.ALLOW, reason="ok", patched_payload={})


def test_helpers() -> None:
    assert Decision.deny("no", "r1").verdict is Verdict.DENY
    assert Decision.escalate("ask", "r2").rule_id == "r2"

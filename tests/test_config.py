from pathlib import Path

import pytest
from pydantic import ValidationError

from warden.config import WardenConfig, load_config
from warden.config.schema import FailMode, Mode

EXAMPLE = Path(__file__).parent.parent / "examples" / "warden.yaml"


def minimal() -> dict[str, object]:
    return {
        "listeners": [{"type": "stdio"}],
        "upstreams": {"s": {"kind": "mcp_stdio", "command": "echo"}},
        "policy": {"address": "localhost:1"},
    }


def test_example_config_loads() -> None:
    cfg = load_config(EXAMPLE)
    assert cfg.mode is Mode.ENFORCE
    assert cfg.policy.fail_mode_overrides[0].fail_mode is FailMode.OPEN
    assert [d.name for d in cfg.detectors] == ["pii", "injection"]


def test_defaults() -> None:
    cfg = WardenConfig.model_validate(
        {**minimal(), "identity": {"method": "static", "static_agent_id": "a"}}
    )
    assert cfg.mode is Mode.ENFORCE
    assert cfg.policy.fail_mode is FailMode.CLOSED
    assert cfg.session_store.type == "memory"


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        WardenConfig.model_validate({**minimal(), "polcy": {}})


def test_identity_requires_method_fields() -> None:
    with pytest.raises(ValidationError):
        WardenConfig.model_validate({**minimal(), "identity": {"method": "jwt"}})


def test_duplicate_detectors_rejected() -> None:
    det = {"name": "pii", "address": "x:1"}
    with pytest.raises(ValidationError, match="duplicate"):
        WardenConfig.model_validate({**minimal(), "detectors": [det, det]})


def test_http_listener_needs_port() -> None:
    with pytest.raises(ValidationError):
        WardenConfig.model_validate(
            {**minimal(), "listeners": [{"type": "http", "protocol": "mcp"}]}
        )

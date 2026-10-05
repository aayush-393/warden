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


def test_single_upstream_is_the_default_target() -> None:
    cfg = WardenConfig.model_validate(minimal())
    assert cfg.upstream_name(cfg.listeners[0]) == "s"


def test_listener_must_name_upstream_when_ambiguous() -> None:
    raw = minimal()
    raw["upstreams"] = {
        "a": {"kind": "mcp_stdio", "command": "x"},
        "b": {"kind": "mcp_stdio", "command": "y"},
    }
    with pytest.raises(ValidationError, match="must set `upstream`"):
        WardenConfig.model_validate(raw)
    raw["listeners"] = [{"type": "stdio", "upstream": "b"}]
    assert (
        WardenConfig.model_validate(raw).upstream_name(
            WardenConfig.model_validate(raw).listeners[0]
        )
        == "b"
    )


def test_unknown_upstream_reference_rejected() -> None:
    raw = {**minimal(), "listeners": [{"type": "stdio", "upstream": "nope"}]}
    with pytest.raises(ValidationError, match="unknown upstream"):
        WardenConfig.model_validate(raw)


def test_listener_and_upstream_transports_must_match() -> None:
    raw = {**minimal(), "listeners": [{"type": "http", "protocol": "mcp", "port": 9000}]}
    with pytest.raises(ValidationError, match="cannot proxy"):
        WardenConfig.model_validate(raw)


def test_stdio_listener_cannot_be_combined() -> None:
    http = {"type": "http", "protocol": "mcp", "port": 9000}
    raw = {**minimal(), "listeners": [{"type": "stdio"}, http]}
    with pytest.raises(ValidationError, match="cannot be combined"):
        WardenConfig.model_validate(raw)


def test_relative_paths_resolve_against_config_dir(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "conf"
    cfg_dir.mkdir()
    cfg = cfg_dir / "warden.yaml"
    cfg.write_text(
        "listeners: [{type: stdio}]\n"
        "upstreams: {s: {kind: mcp_stdio, command: echo}}\n"
        "policy: {address: 'x:1', policy_dir: ./policies}\n"
        "observability: {log_file: logs/warden.log}\n"
        "audit: {sqlite_path: /abs/audit.db}\n"
    )
    loaded = load_config(cfg)
    assert loaded.observability.log_file == cfg_dir.resolve() / "logs/warden.log"
    assert loaded.policy.policy_dir == cfg_dir.resolve() / "policies"
    assert loaded.audit.sqlite_path == Path("/abs/audit.db")  # absolute paths untouched


def test_cli_reports_unwritable_log_file_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from warden.cli import main

    cfg = tmp_path / "warden.yaml"
    cfg.write_text(
        "listeners: [{type: stdio}]\n"
        "upstreams: {s: {kind: mcp_stdio, command: echo}}\n"
        "policy: {address: 'x:1'}\n"
        "observability: {log_file: no/such/dir/warden.log}\n"
    )
    assert main(["run", "-c", str(cfg)]) == 2
    assert "cannot open log file" in capsys.readouterr().err

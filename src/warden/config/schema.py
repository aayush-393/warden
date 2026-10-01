"""YAML config schema. Everything is validated up front so bad config fails at startup."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mode(StrEnum):
    ENFORCE = "enforce"
    DRY_RUN = "dry_run"  # evaluate and log, never block or modify
    BYPASS = "bypass"  # forward untouched, audit only


class FailMode(StrEnum):
    CLOSED = "closed"  # plugin error/timeout -> deny
    OPEN = "open"  # plugin error/timeout -> allow


# --- listeners (agent-facing) -------------------------------------------------


class StdioListener(_Model):
    type: Literal["stdio"] = "stdio"


class HttpListener(_Model):
    type: Literal["http"] = "http"
    protocol: Literal["mcp", "a2a"]
    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)]


Listener = Annotated[StdioListener | HttpListener, Field(discriminator="type")]


# --- upstreams ----------------------------------------------------------------


class McpStdioUpstream(_Model):
    kind: Literal["mcp_stdio"] = "mcp_stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class McpHttpUpstream(_Model):
    kind: Literal["mcp_http"] = "mcp_http"
    url: str


class A2aUpstream(_Model):
    kind: Literal["a2a"] = "a2a"
    url: str


Upstream = Annotated[McpStdioUpstream | McpHttpUpstream | A2aUpstream, Field(discriminator="kind")]


# --- identity -----------------------------------------------------------------


class Identity(_Model):
    method: Literal["static", "jwt", "mtls"] = "static"
    # static: the agent id to assume. jwt/mtls derive it from the credential.
    static_agent_id: str | None = None
    jwt_jwks_url: str | None = None
    jwt_audience: str | None = None
    mtls_ca_file: Path | None = None

    @model_validator(mode="after")
    def _check_method_fields(self) -> Self:
        if self.method == "static" and not self.static_agent_id:
            raise ValueError("identity.static_agent_id is required when method is 'static'")
        if self.method == "jwt" and not self.jwt_jwks_url:
            raise ValueError("identity.jwt_jwks_url is required when method is 'jwt'")
        if self.method == "mtls" and not self.mtls_ca_file:
            raise ValueError("identity.mtls_ca_file is required when method is 'mtls'")
        return self


# --- plugins (gRPC) -----------------------------------------------------------


class PluginEndpoint(_Model):
    address: str  # host:port or unix:/path
    timeout_ms: Annotated[int, Field(gt=0)] = 500
    fail_mode: FailMode = FailMode.CLOSED


class FailModeOverride(_Model):
    """Per-tool fail mode, so low-risk tools can fail open while the default stays closed."""

    server: str = "*"
    tool: str = "*"
    fail_mode: FailMode


class Policy(PluginEndpoint):
    backend: Literal["cedar", "rego"] = "cedar"
    policy_dir: Path | None = None  # local policy files the service loads
    fail_mode_overrides: list[FailModeOverride] = Field(default_factory=list[FailModeOverride])


class Detector(PluginEndpoint):
    name: str
    # Which direction(s) the detector inspects.
    directions: list[Literal["request", "response"]] = Field(
        default_factory=lambda: ["request", "response"]
    )


class Approval(PluginEndpoint):
    # How long a parked call waits for a human before `on_timeout` applies.
    wait_timeout_s: Annotated[int, Field(gt=0)] = 300
    on_timeout: Literal["deny", "allow"] = "deny"
    # Approval is a human-in-the-loop path: the gRPC call itself is long-lived.
    timeout_ms: Annotated[int, Field(gt=0)] = 10_000


# --- state, audit, observability ----------------------------------------------


class MemorySessionStore(_Model):
    type: Literal["memory"] = "memory"


class RedisSessionStore(_Model):
    type: Literal["redis"] = "redis"
    url: str
    ttl_s: Annotated[int, Field(gt=0)] = 3600


SessionStore = Annotated[MemorySessionStore | RedisSessionStore, Field(discriminator="type")]


class Audit(_Model):
    sqlite_path: Path = Path("warden-audit.db")
    # Persist full payloads, or only a hash (for sensitive deployments).
    store_payloads: bool = True


class Observability(_Model):
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    otlp_endpoint: str | None = None


# --- root ---------------------------------------------------------------------


class WardenConfig(_Model):
    version: Literal[1] = 1
    mode: Mode = Mode.ENFORCE
    listeners: list[Listener] = Field(min_length=1)
    # Named upstreams; names are what policy refers to as the resource's `server`.
    upstreams: dict[str, Upstream] = Field(min_length=1)
    identity: Identity = Field(default_factory=lambda: Identity(static_agent_id="default"))
    policy: Policy
    detectors: list[Detector] = Field(default_factory=list[Detector])
    approval: Approval | None = None
    session_store: SessionStore = Field(default_factory=MemorySessionStore)
    audit: Audit = Field(default_factory=Audit)
    observability: Observability = Field(default_factory=Observability)

    @model_validator(mode="after")
    def _check_unique_detectors(self) -> Self:
        names = [d.name for d in self.detectors]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate detector names: {sorted(dupes)}")
        return self


def load_config(path: str | Path) -> WardenConfig:
    """Parse and validate a YAML config file. Raises pydantic.ValidationError on bad input."""
    raw = yaml.safe_load(Path(path).read_text())
    return WardenConfig.model_validate(raw)

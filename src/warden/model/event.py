"""Internal event model: the protocol-neutral shape every adapter normalizes into."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Direction(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"


class Protocol(StrEnum):
    MCP = "mcp"
    A2A = "a2a"


class Action(StrEnum):
    # MCP
    INITIALIZE = "initialize"
    LIST_TOOLS = "list_tools"
    CALL_TOOL = "call_tool"
    LIST_RESOURCES = "list_resources"
    READ_RESOURCE = "read_resource"
    LIST_PROMPTS = "list_prompts"
    GET_PROMPT = "get_prompt"
    SAMPLE = "sample"
    # A2A
    SEND_MESSAGE = "send_message"
    GET_TASK = "get_task"
    CANCEL_TASK = "cancel_task"
    # Anything we cannot classify; policy decides (default deny is recommended).
    OTHER = "other"


class ResourceKind(StrEnum):
    SERVER = "server"
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"
    PEER_AGENT = "peer_agent"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Actor(_Frozen):
    """The authenticated agent on whose behalf the message flows."""

    agent_id: str
    # How the identity was established (e.g. "mtls", "jwt", "static", "anonymous").
    auth_method: str = "anonymous"
    claims: dict[str, Any] = Field(default_factory=dict)


class Resource(_Frozen):
    """What the action targets: a server, a tool on a server, or a peer agent."""

    kind: ResourceKind
    # Upstream server or peer agent name as configured in Warden.
    server: str
    # Tool / resource URI / prompt name, when the action targets one.
    name: str | None = None


class CallRecord(_Frozen):
    """One prior step in a session, used by history-aware policy."""

    event_id: str
    action: Action
    resource: Resource
    decision: str
    at: datetime


class SessionContext(_Frozen):
    """Per-session state visible to policy and detectors."""

    session_id: str
    # Taint labels accumulated so far, e.g. "untrusted_content", "pii".
    taint_labels: frozenset[str] = frozenset()
    history: tuple[CallRecord, ...] = ()


class Event(_Frozen):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    # Ties a response event back to the request that produced it.
    correlation_id: str | None = None
    direction: Direction
    protocol: Protocol
    actor: Actor
    action: Action
    resource: Resource
    # Raw protocol payload (JSON-RPC params for requests, result/error for responses).
    payload: dict[str, Any] = Field(default_factory=dict)
    session: SessionContext
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

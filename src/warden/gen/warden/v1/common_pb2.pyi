import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Direction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DIRECTION_UNSPECIFIED: _ClassVar[Direction]
    DIRECTION_REQUEST: _ClassVar[Direction]
    DIRECTION_RESPONSE: _ClassVar[Direction]

class Protocol(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PROTOCOL_UNSPECIFIED: _ClassVar[Protocol]
    PROTOCOL_MCP: _ClassVar[Protocol]
    PROTOCOL_A2A: _ClassVar[Protocol]

class ResourceKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESOURCE_KIND_UNSPECIFIED: _ClassVar[ResourceKind]
    RESOURCE_KIND_SERVER: _ClassVar[ResourceKind]
    RESOURCE_KIND_TOOL: _ClassVar[ResourceKind]
    RESOURCE_KIND_RESOURCE: _ClassVar[ResourceKind]
    RESOURCE_KIND_PROMPT: _ClassVar[ResourceKind]
    RESOURCE_KIND_PEER_AGENT: _ClassVar[ResourceKind]

class Verdict(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VERDICT_UNSPECIFIED: _ClassVar[Verdict]
    VERDICT_ALLOW: _ClassVar[Verdict]
    VERDICT_DENY: _ClassVar[Verdict]
    VERDICT_MODIFY: _ClassVar[Verdict]
    VERDICT_ESCALATE: _ClassVar[Verdict]
DIRECTION_UNSPECIFIED: Direction
DIRECTION_REQUEST: Direction
DIRECTION_RESPONSE: Direction
PROTOCOL_UNSPECIFIED: Protocol
PROTOCOL_MCP: Protocol
PROTOCOL_A2A: Protocol
RESOURCE_KIND_UNSPECIFIED: ResourceKind
RESOURCE_KIND_SERVER: ResourceKind
RESOURCE_KIND_TOOL: ResourceKind
RESOURCE_KIND_RESOURCE: ResourceKind
RESOURCE_KIND_PROMPT: ResourceKind
RESOURCE_KIND_PEER_AGENT: ResourceKind
VERDICT_UNSPECIFIED: Verdict
VERDICT_ALLOW: Verdict
VERDICT_DENY: Verdict
VERDICT_MODIFY: Verdict
VERDICT_ESCALATE: Verdict

class Actor(_message.Message):
    __slots__ = ("agent_id", "auth_method", "claims")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    AUTH_METHOD_FIELD_NUMBER: _ClassVar[int]
    CLAIMS_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    auth_method: str
    claims: _struct_pb2.Struct
    def __init__(self, agent_id: _Optional[str] = ..., auth_method: _Optional[str] = ..., claims: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class Resource(_message.Message):
    __slots__ = ("kind", "server", "name")
    KIND_FIELD_NUMBER: _ClassVar[int]
    SERVER_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    kind: ResourceKind
    server: str
    name: str
    def __init__(self, kind: _Optional[_Union[ResourceKind, str]] = ..., server: _Optional[str] = ..., name: _Optional[str] = ...) -> None: ...

class CallRecord(_message.Message):
    __slots__ = ("event_id", "action", "resource", "decision", "at")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    action: str
    resource: Resource
    decision: str
    at: _timestamp_pb2.Timestamp
    def __init__(self, event_id: _Optional[str] = ..., action: _Optional[str] = ..., resource: _Optional[_Union[Resource, _Mapping]] = ..., decision: _Optional[str] = ..., at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SessionContext(_message.Message):
    __slots__ = ("session_id", "taint_labels", "history")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TAINT_LABELS_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    taint_labels: _containers.RepeatedScalarFieldContainer[str]
    history: _containers.RepeatedCompositeFieldContainer[CallRecord]
    def __init__(self, session_id: _Optional[str] = ..., taint_labels: _Optional[_Iterable[str]] = ..., history: _Optional[_Iterable[_Union[CallRecord, _Mapping]]] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("event_id", "correlation_id", "direction", "protocol", "actor", "action", "resource", "payload", "session", "timestamp")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    PROTOCOL_FIELD_NUMBER: _ClassVar[int]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    correlation_id: str
    direction: Direction
    protocol: Protocol
    actor: Actor
    action: str
    resource: Resource
    payload: _struct_pb2.Struct
    session: SessionContext
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, event_id: _Optional[str] = ..., correlation_id: _Optional[str] = ..., direction: _Optional[_Union[Direction, str]] = ..., protocol: _Optional[_Union[Protocol, str]] = ..., actor: _Optional[_Union[Actor, _Mapping]] = ..., action: _Optional[str] = ..., resource: _Optional[_Union[Resource, _Mapping]] = ..., payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., session: _Optional[_Union[SessionContext, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class Decision(_message.Message):
    __slots__ = ("verdict", "reason", "rule_id", "patched_payload", "add_taint")
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PATCHED_PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    ADD_TAINT_FIELD_NUMBER: _ClassVar[int]
    verdict: Verdict
    reason: str
    rule_id: str
    patched_payload: _struct_pb2.Struct
    add_taint: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, verdict: _Optional[_Union[Verdict, str]] = ..., reason: _Optional[str] = ..., rule_id: _Optional[str] = ..., patched_payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., add_taint: _Optional[_Iterable[str]] = ...) -> None: ...

from warden.gen.warden.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Severity(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEVERITY_UNSPECIFIED: _ClassVar[Severity]
    SEVERITY_LOW: _ClassVar[Severity]
    SEVERITY_MEDIUM: _ClassVar[Severity]
    SEVERITY_HIGH: _ClassVar[Severity]
    SEVERITY_CRITICAL: _ClassVar[Severity]
SEVERITY_UNSPECIFIED: Severity
SEVERITY_LOW: Severity
SEVERITY_MEDIUM: Severity
SEVERITY_HIGH: Severity
SEVERITY_CRITICAL: Severity

class InspectRequest(_message.Message):
    __slots__ = ("event",)
    EVENT_FIELD_NUMBER: _ClassVar[int]
    event: _common_pb2.Event
    def __init__(self, event: _Optional[_Union[_common_pb2.Event, _Mapping]] = ...) -> None: ...

class Finding(_message.Message):
    __slots__ = ("type", "severity", "confidence", "location", "detail")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    type: str
    severity: Severity
    confidence: float
    location: str
    detail: str
    def __init__(self, type: _Optional[str] = ..., severity: _Optional[_Union[Severity, str]] = ..., confidence: _Optional[float] = ..., location: _Optional[str] = ..., detail: _Optional[str] = ...) -> None: ...

class InspectResponse(_message.Message):
    __slots__ = ("findings", "proposed_decision", "add_taint")
    FINDINGS_FIELD_NUMBER: _ClassVar[int]
    PROPOSED_DECISION_FIELD_NUMBER: _ClassVar[int]
    ADD_TAINT_FIELD_NUMBER: _ClassVar[int]
    findings: _containers.RepeatedCompositeFieldContainer[Finding]
    proposed_decision: _common_pb2.Decision
    add_taint: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, findings: _Optional[_Iterable[_Union[Finding, _Mapping]]] = ..., proposed_decision: _Optional[_Union[_common_pb2.Decision, _Mapping]] = ..., add_taint: _Optional[_Iterable[str]] = ...) -> None: ...

class DescribeRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DescribeResponse(_message.Message):
    __slots__ = ("name", "version")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    name: str
    version: str
    def __init__(self, name: _Optional[str] = ..., version: _Optional[str] = ...) -> None: ...

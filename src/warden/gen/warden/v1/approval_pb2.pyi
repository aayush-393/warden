from warden.gen.warden.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ApprovalOutcome(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    APPROVAL_OUTCOME_UNSPECIFIED: _ClassVar[ApprovalOutcome]
    APPROVAL_OUTCOME_APPROVED: _ClassVar[ApprovalOutcome]
    APPROVAL_OUTCOME_REJECTED: _ClassVar[ApprovalOutcome]
    APPROVAL_OUTCOME_TIMED_OUT: _ClassVar[ApprovalOutcome]
APPROVAL_OUTCOME_UNSPECIFIED: ApprovalOutcome
APPROVAL_OUTCOME_APPROVED: ApprovalOutcome
APPROVAL_OUTCOME_REJECTED: ApprovalOutcome
APPROVAL_OUTCOME_TIMED_OUT: ApprovalOutcome

class RequestApprovalRequest(_message.Message):
    __slots__ = ("event", "reason", "rule_id", "wait_timeout_s")
    EVENT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    WAIT_TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    event: _common_pb2.Event
    reason: str
    rule_id: str
    wait_timeout_s: int
    def __init__(self, event: _Optional[_Union[_common_pb2.Event, _Mapping]] = ..., reason: _Optional[str] = ..., rule_id: _Optional[str] = ..., wait_timeout_s: _Optional[int] = ...) -> None: ...

class RequestApprovalResponse(_message.Message):
    __slots__ = ("outcome", "approver", "comment")
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    APPROVER_FIELD_NUMBER: _ClassVar[int]
    COMMENT_FIELD_NUMBER: _ClassVar[int]
    outcome: ApprovalOutcome
    approver: str
    comment: str
    def __init__(self, outcome: _Optional[_Union[ApprovalOutcome, str]] = ..., approver: _Optional[str] = ..., comment: _Optional[str] = ...) -> None: ...

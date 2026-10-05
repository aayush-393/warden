"""Minimal JSON-RPC 2.0 classification for observing MCP traffic.

The proxy forwards raw bytes untouched; this module only inspects them so that
correlation and logging never alter what goes over the wire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

# JSON-RPC ids are strings or integers. 1 and "1" are different ids, so keys carry the type.
type RequestId = str | int
type IdKey = tuple[str, RequestId]


class Kind(StrEnum):
    REQUEST = "request"
    NOTIFICATION = "notification"
    RESPONSE = "response"  # result
    ERROR = "error"  # error response
    INVALID = "invalid"


def as_dict(value: Any) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def id_key(value: RequestId) -> IdKey:
    return (type(value).__name__, value)


@dataclass(frozen=True, slots=True)
class Message:
    kind: Kind
    id: RequestId | None = None
    method: str | None = None
    params: Any = None
    # Raw decoded object, kept for debug-level payload logging.
    body: Any = None

    @property
    def id_key(self) -> IdKey | None:
        return None if self.id is None else id_key(self.id)

    @property
    def error_code(self) -> int | None:
        if self.kind is not Kind.ERROR:
            return None
        err = (as_dict(self.body) or {}).get("error")
        code = (as_dict(err) or {}).get("code")
        return code if isinstance(code, int) else None


def classify(obj: Any) -> Message:
    d = as_dict(obj)
    if d is None:
        return Message(Kind.INVALID, body=obj)
    raw_id = d.get("id")
    msg_id = raw_id if isinstance(raw_id, str | int) and not isinstance(raw_id, bool) else None
    method = d.get("method")
    if isinstance(method, str):
        if "id" not in d:
            return Message(Kind.NOTIFICATION, method=method, params=d.get("params"), body=d)
        if msg_id is None:  # a request must carry a usable id
            return Message(Kind.INVALID, method=method, body=d)
        return Message(Kind.REQUEST, id=msg_id, method=method, params=d.get("params"), body=d)
    if "result" in d:
        return Message(Kind.RESPONSE, id=msg_id, body=d)
    if "error" in d:
        return Message(Kind.ERROR, id=msg_id, body=d)
    return Message(Kind.INVALID, body=d)


def parse(raw: bytes | str) -> list[Message]:
    """Decode one frame into messages (a JSON-RPC batch yields several).

    Raises ValueError on malformed JSON.
    """
    obj = json.loads(raw)
    if isinstance(obj, list):
        return [classify(item) for item in cast("list[Any]", obj)]
    return [classify(obj)]

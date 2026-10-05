"""Incremental Server-Sent Events parser, used only to *observe* a stream.

The proxy relays upstream bytes untouched; this parser sees the same bytes and
extracts event data so JSON-RPC messages inside the stream can be logged/correlated.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SseEvent:
    data: str
    event: str | None = None
    id: str | None = None


class SseParser:
    def __init__(self) -> None:
        self._buf = b""
        self._data: list[str] = []
        self._event: str | None = None
        self._id: str | None = None

    def feed(self, chunk: bytes) -> Iterator[SseEvent]:
        self._buf += chunk
        # Lines end in \n, \r\n or \r. A trailing \r may be half of \r\n, so hold it back.
        while True:
            idx = _line_end(self._buf)
            if idx is None:
                return
            line, self._buf = self._buf[: idx[0]], self._buf[idx[1] :]
            ev = self._line(line.decode("utf-8", errors="replace"))
            if ev is not None:
                yield ev

    def _line(self, line: str) -> SseEvent | None:
        if line == "":
            if not self._data:
                self._event = None
                return None
            ev = SseEvent("\n".join(self._data), self._event, self._id)
            self._data, self._event = [], None
            return ev
        if line.startswith(":"):
            return None
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        match name:
            case "data":
                self._data.append(value)
            case "event":
                self._event = value
            case "id":
                self._id = value
            case _:  # "retry" and unknown fields don't affect event data
                pass
        return None


def _line_end(buf: bytes) -> tuple[int, int] | None:
    """Return (end_of_line, start_of_next_line) for the first complete line, else None."""
    for i, b in enumerate(buf):
        if b == 0x0A:
            return i, i + 1
        if b == 0x0D:
            if i + 1 >= len(buf):
                return None  # might be \r\n; wait for more
            return (i, i + 2) if buf[i + 1] == 0x0A else (i, i + 1)
    return None

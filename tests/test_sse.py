from warden.mcp.sse import SseParser


def events(*chunks: bytes):
    p = SseParser()
    return [e for c in chunks for e in p.feed(c)]


def test_basic_event() -> None:
    [e] = events(b'id: 7\nevent: message\ndata: {"a":1}\n\n')
    assert (e.id, e.event, e.data) == ("7", "message", '{"a":1}')


def test_split_across_chunks_and_crlf() -> None:
    [e] = events(b"data: hel", b"lo\r", b"\n\r", b"\n")
    assert e.data == "hello"


def test_multiline_data_and_comments() -> None:
    [e] = events(b": keepalive\ndata: a\ndata: b\n\n")
    assert e.data == "a\nb"


def test_priming_event_has_empty_data() -> None:
    [e] = events(b"id: 1\ndata:\n\n")
    assert (e.id, e.data) == ("1", "")


def test_blank_lines_without_data_emit_nothing() -> None:
    assert events(b"\n\n: just a comment\n\n") == []

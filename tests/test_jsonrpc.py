import pytest

from warden.mcp.jsonrpc import Kind, parse


def test_classifies_each_kind() -> None:
    [req] = parse(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
    [note] = parse(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
    [ok] = parse(b'{"jsonrpc":"2.0","id":1,"result":{}}')
    [err] = parse(b'{"jsonrpc":"2.0","id":"a","error":{"code":-32601,"message":"x"}}')
    assert (req.kind, req.method, req.id) == (Kind.REQUEST, "tools/list", 1)
    assert note.kind is Kind.NOTIFICATION and note.id is None
    assert ok.kind is Kind.RESPONSE
    assert err.kind is Kind.ERROR and err.error_code == -32601


def test_int_and_string_ids_are_distinct() -> None:
    [a] = parse(b'{"id":1,"result":{}}')
    [b] = parse(b'{"id":"1","result":{}}')
    assert a.id_key != b.id_key


def test_id_zero_is_a_valid_id() -> None:
    [req] = parse(b'{"id":0,"method":"ping"}')
    assert req.kind is Kind.REQUEST and req.id == 0


def test_request_with_null_id_is_invalid() -> None:
    [msg] = parse(b'{"id":null,"method":"ping"}')
    assert msg.kind is Kind.INVALID


def test_batch() -> None:
    msgs = parse(b'[{"id":1,"method":"a"},{"method":"b"}]')
    assert [m.kind for m in msgs] == [Kind.REQUEST, Kind.NOTIFICATION]


def test_malformed_json_raises() -> None:
    with pytest.raises(ValueError):
        parse(b"{nope")

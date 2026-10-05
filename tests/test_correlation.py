from warden.mcp.correlation import Correlator, Flow
from warden.mcp.jsonrpc import parse

C2S, S2C = Flow.CLIENT_TO_SERVER, Flow.SERVER_TO_CLIENT


def feed(c: Correlator, flow: Flow, raw: str):
    [msg] = parse(raw)
    return c.observe(flow, msg)


def test_response_matches_request_with_latency() -> None:
    c = Correlator()
    feed(c, C2S, '{"id":1,"method":"tools/call"}')
    obs = feed(c, S2C, '{"id":1,"result":{}}')
    assert obs.request_method == "tools/call"
    assert obs.latency_s is not None and obs.latency_s >= 0
    assert c.pending_count() == 0


def test_id_spaces_are_independent_per_direction() -> None:
    """Client and server both use id 1; each response must match its own side's request."""
    c = Correlator()
    feed(c, C2S, '{"id":1,"method":"tools/call"}')
    feed(c, S2C, '{"id":1,"method":"sampling/createMessage"}')
    assert feed(c, C2S, '{"id":1,"result":{}}').request_method == "sampling/createMessage"
    assert feed(c, S2C, '{"id":1,"result":{}}').request_method == "tools/call"


def test_unmatched_response() -> None:
    assert feed(Correlator(), S2C, '{"id":9,"result":{}}').unmatched


def test_error_response_matches() -> None:
    c = Correlator()
    feed(c, C2S, '{"id":"x","method":"m"}')
    obs = feed(c, S2C, '{"id":"x","error":{"code":-1,"message":"boom"}}')
    assert obs.request_method == "m" and not obs.unmatched


def test_client_cancel_retires_client_request() -> None:
    c = Correlator()
    feed(c, C2S, '{"id":5,"method":"tools/call"}')
    obs = feed(c, C2S, '{"method":"notifications/cancelled","params":{"requestId":5}}')
    assert obs.cancelled_method == "tools/call"
    assert c.pending_count() == 0
    # A late response is reported as unmatched rather than mis-correlated.
    assert feed(c, S2C, '{"id":5,"result":{}}').unmatched


def test_server_cancel_retires_server_request() -> None:
    c = Correlator()
    feed(c, C2S, '{"id":5,"method":"tools/call"}')
    feed(c, S2C, '{"id":5,"method":"sampling/createMessage"}')
    obs = feed(c, S2C, '{"method":"notifications/cancelled","params":{"requestId":5}}')
    assert obs.cancelled_method == "sampling/createMessage"
    assert c.pending_count(C2S) == 1  # the client's own request 5 is untouched


def test_pending_table_is_bounded() -> None:
    c = Correlator(max_pending=3)
    for i in range(10):
        feed(c, C2S, f'{{"id":{i},"method":"m"}}')
    assert c.pending_count() == 3

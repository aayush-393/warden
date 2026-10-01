from warden.gen.warden.v1 import approval_pb2, common_pb2, detector_pb2, policy_pb2


def test_policy_request_roundtrip() -> None:
    ev = common_pb2.Event(
        event_id="e1",
        direction=common_pb2.DIRECTION_REQUEST,
        actor=common_pb2.Actor(agent_id="a"),
    )
    ev.payload.update({"k": "v"})
    req = policy_pb2.EvaluateRequest(event=ev)
    assert policy_pb2.EvaluateRequest.FromString(req.SerializeToString()).event.payload["k"] == "v"


def test_services_importable() -> None:
    assert detector_pb2.DESCRIPTOR.services_by_name["DetectorService"]
    assert approval_pb2.DESCRIPTOR.services_by_name["ApprovalService"]

"""A tiny scripted MCP stdio server used by the proxy tests (stdlib only)."""

import json
import sys


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def result(msg_id, value) -> None:
    send({"jsonrpc": "2.0", "id": msg_id, "result": value})


print("fake-server booted", file=sys.stderr, flush=True)

while line := sys.stdin.readline():
    msg = json.loads(line)
    method, msg_id = msg.get("method"), msg.get("id")
    if method == "initialize":
        result(msg_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}})
    elif method == "ping":
        result(msg_id, {})
    elif method == "tools/call":
        name = msg["params"]["name"]
        if name == "echo":
            result(msg_id, {"content": [{"type": "text", "text": msg["params"]["arguments"]["t"]}]})
        elif name == "sample":
            # Server-to-client request while the client's call is still outstanding.
            send(
                {
                    "jsonrpc": "2.0",
                    "id": "srv-1",
                    "method": "sampling/createMessage",
                    "params": {"messages": []},
                }
            )
            reply = json.loads(sys.stdin.readline())
            result(msg_id, {"sampled": reply["result"]})
        # "hang": never answer
    elif method == "notifications/cancelled":
        send({"jsonrpc": "2.0", "method": "notifications/saw_cancel", "params": msg["params"]})
    elif msg_id is not None:
        send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "nope"}})

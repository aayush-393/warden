# Warden

Policy, privacy, and approvals for AI agents. Warden sits between an agent and its MCP servers / peer agents, and runs every message (both directions) through an interceptor pipeline: authn → policy → input filters → forward → output filters → audit.

Status: early development (M0: foundations).

## Layout

- `src/warden/model/`: internal event and decision models
- `src/warden/config/`: Pydantic-validated YAML config (see `examples/warden.yaml`)
- `proto/warden/v1/`: gRPC contracts for the policy, detector, and approval plugins
- `src/warden/gen/`: generated Python stubs (do not edit; run `scripts/gen_proto.sh`)

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
./scripts/gen_proto.sh   # after editing .proto files
pre-commit install
```

## License

Apache-2.0

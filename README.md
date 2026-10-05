# Warden

Policy, privacy, and approvals for AI agents. Warden sits between an agent and its MCP servers / peer agents, and runs every message (both directions) through an interceptor pipeline: authn → policy → input filters → forward → output filters → audit.

Status: early development. M0 (foundations) and M1 (transparent MCP proxy) are in place; policy, detectors and approvals are not wired in yet.

## Layout

- `src/warden/model/`: internal event and decision models
- `src/warden/mcp/`: transparent MCP proxy (stdio and streamable HTTP), correlation, SSE parsing
- `src/warden/config/`: Pydantic-validated YAML config (see `examples/warden.yaml`)
- `proto/warden/v1/`: gRPC contracts for the policy, detector, and approval plugins
- `src/warden/gen/`: generated Python stubs (do not edit; run `scripts/gen_proto.sh`)

## Using it

Warden sits in front of one MCP server. Point it at a config (see `examples/warden.yaml`):

```sh
uv run warden validate -c warden.yaml
uv run warden run -c warden.yaml
```

**stdio** (Claude Desktop, Claude Code): the agent launches Warden, which launches the real server.
Replace the server's command with Warden and move the original into the config's `upstreams`:

```json
{ "mcpServers": { "filesystem": { "command": "uv", "args": ["run", "--project", "/path/to/warden", "warden", "run", "-c", "/path/to/warden.yaml"] } } }
```

**Streamable HTTP**: use an `http` listener with an `mcp_http` upstream, then point the agent at
`http://<host>:<port>/<upstream path>`. Only the upstream's MCP endpoint is proxied; other paths
(e.g. OAuth discovery) return 404 for now. Browser requests with a foreign `Origin` are rejected.

Frames are relayed byte-for-byte; Warden only observes them in M1. Both directions run independently, so
server-initiated requests (sampling, elicitation, roots) work. Logs are JSON lines on stderr
(and `observability.log_file`); stdout is reserved for the protocol. Set `log_level: debug` to
include full payloads. Relative paths in the config resolve against the config file's directory.

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

#!/usr/bin/env bash
# Regenerate Python gRPC stubs from proto/ into src/warden/gen.
# Uses grpcio-tools so no extra binaries are needed; `buf lint` runs separately in CI.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf src/warden/gen && mkdir -p src/warden/gen
uv run python -m grpc_tools.protoc -Iproto \
  --python_out=src/warden/gen --pyi_out=src/warden/gen --grpc_python_out=src/warden/gen \
  proto/warden/v1/*.proto
# protoc emits `from warden.v1 import x_pb2`; rewrite to the packaged location.
find src/warden/gen -name '*.py' -o -name '*.pyi' | xargs sed -i.bak 's/^from warden\.v1 import/from warden.gen.warden.v1 import/'
find src/warden/gen -name '*.bak' -delete
find src/warden/gen -type d -exec touch {}/__init__.py \;

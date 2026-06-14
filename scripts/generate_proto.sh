#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/generated"

mkdir -p "$OUT_DIR"
"$PYTHON" -m grpc_tools.protoc \
  -I"$ROOT_DIR/proto" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$ROOT_DIR/proto/flight.proto"

sed -i '' 's/^import flight_pb2 as flight__pb2/from generated import flight_pb2 as flight__pb2/' "$OUT_DIR/flight_pb2_grpc.py" 2>/dev/null \
  || sed -i 's/^import flight_pb2 as flight__pb2/from generated import flight_pb2 as flight__pb2/' "$OUT_DIR/flight_pb2_grpc.py"

touch "$OUT_DIR/__init__.py"
echo "Generated gRPC code in $OUT_DIR"

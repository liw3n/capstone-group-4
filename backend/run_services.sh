#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

python mcp/server.py &
mcp_pid=$!
api_pid=""

cleanup() {
    kill "$mcp_pid" 2>/dev/null || true
    if [[ -n "$api_pid" ]]; then
        kill "$api_pid" 2>/dev/null || true
    fi
    wait "$mcp_pid" 2>/dev/null || true
    if [[ -n "$api_pid" ]]; then
        wait "$api_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

mcp_ready=false
for attempt in {1..60}; do
    if ! kill -0 "$mcp_pid" 2>/dev/null; then
        wait "$mcp_pid"
    fi
    if python -c 'import socket; s = socket.create_connection(("127.0.0.1", 8001), timeout=0.2); s.close()' 2>/dev/null; then
        mcp_ready=true
        break
    fi
    sleep 0.25
done
if [[ "$mcp_ready" != true ]]; then
    printf 'FastMCP did not become ready on port 8001.\n' >&2
    exit 1
fi

python -m uvicorn app.main:app --host 0.0.0.0 --port 4000 &
api_pid=$!
while kill -0 "$mcp_pid" 2>/dev/null && kill -0 "$api_pid" 2>/dev/null; do
    sleep 1
done

if ! kill -0 "$mcp_pid" 2>/dev/null; then
    wait "$mcp_pid"
else
    wait "$api_pid"
fi
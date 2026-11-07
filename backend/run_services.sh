#!/usr/bin/env bash
set -euo pipefail
BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"
export PYTHONUNBUFFERED=1
printf '[startup] Launching service supervisor.\n'
exec python -u service_runner.py

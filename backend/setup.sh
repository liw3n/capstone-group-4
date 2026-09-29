#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FAKECLOUD_PID_FILE="$BACKEND_DIR/.fakecloud.pid"
FAKECLOUD_LOG_FILE="$BACKEND_DIR/.fakecloud.log"

cd "$BACKEND_DIR"

for required_command in uv fakecloud terraform nc; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$required_command" >&2
        exit 1
    fi
done

if ! nc -z 127.0.0.1 4566; then
    if [[ -f "$FAKECLOUD_PID_FILE" ]] && kill -0 "$(<"$FAKECLOUD_PID_FILE")" 2>/dev/null; then
        printf 'FakeCloud is already starting (PID %s).\n' "$(<"$FAKECLOUD_PID_FILE")"
    else
        nohup fakecloud >"$FAKECLOUD_LOG_FILE" 2>&1 </dev/null &
        echo "$!" > "$FAKECLOUD_PID_FILE"
        printf 'Started FakeCloud (PID %s); log: %s\n' "$(<"$FAKECLOUD_PID_FILE")" "$FAKECLOUD_LOG_FILE"
    fi

    for ((attempt = 0; attempt < 60; attempt++)); do
        if nc -z 127.0.0.1 4566; then
            break
        fi
        if ! kill -0 "$(<"$FAKECLOUD_PID_FILE")" 2>/dev/null; then
            printf 'FakeCloud exited before becoming ready. See %s\n' "$FAKECLOUD_LOG_FILE" >&2
            exit 1
        fi
        sleep 1
    done
fi

if ! nc -z 127.0.0.1 4566; then
    printf 'FakeCloud did not become ready on localhost:4566. See %s\n' "$FAKECLOUD_LOG_FILE" >&2
    exit 1
fi

cd "$BACKEND_DIR/terraform"
terraform init
terraform plan
terraform apply
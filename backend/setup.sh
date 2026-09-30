#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FAKECLOUD_PID_FILE="$BACKEND_DIR/.fakecloud.pid"
FAKECLOUD_LOG_FILE="$BACKEND_DIR/.fakecloud.log"

cd "$BACKEND_DIR"

for required_command in uv fakecloud terraform nc psql lsof; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$required_command" >&2
        exit 1
    fi
done

##### Start FakeCloud if not already running #####
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

##### Create AWS resources using Terraform #####
cd "$BACKEND_DIR/terraform"
terraform init
terraform plan
terraform apply

##### Create AWS RDS Tables #####
rds_endpoint="$(terraform output -raw rds_endpoint)"
rds_host="${rds_endpoint%:*}"
rds_port="${rds_endpoint##*:}"
database_url="postgresql://postgres:testpassword@${rds_host}:${rds_port}/pulse"
env_file="$BACKEND_DIR/.env"
env_temp_file="$(mktemp)"

if [[ -f "$env_file" ]]; then
    awk '!/^[[:space:]]*(export[[:space:]]+)?DATABASE_URL[[:space:]]*=/' "$env_file" > "$env_temp_file"
fi
printf 'DATABASE_URL=%s\n' "$database_url" >> "$env_temp_file"
mv "$env_temp_file" "$env_file"

PGPASSWORD=testpassword psql \
    --host "$rds_host" \
    --port "$rds_port" \
    --username postgres \
    --dbname pulse \
    -v ON_ERROR_STOP=1 \
    --file "$BACKEND_DIR/tables/create_campaign_chat_sessions.sql"

##### Deploy App API + MCP #####
cd "$BACKEND_DIR"

start_service() {
    local service_name="$1"
    local service_port="$2"
    local pid_file="$3"
    local log_file="$4"
    shift 4

    local existing_pid=""
    if [[ -f "$pid_file" ]]; then
        existing_pid="$(<"$pid_file")"
        if ! kill -0 "$existing_pid" 2>/dev/null; then
            existing_pid=""
        fi
    fi

    if nc -z 127.0.0.1 "$service_port"; then
        if [[ -n "$existing_pid" ]]; then
            local listener_pids
            listener_pids="$(lsof -tiTCP:"$service_port" -sTCP:LISTEN || true)"
            if [[ -z "$listener_pids" ]]; then
                printf 'Cannot identify the process listening on port %s.\n' "$service_port" >&2
                return 1
            fi

            while IFS= read -r listener_pid; do
                [[ -n "$listener_pid" ]] || continue
                local listener_parent
                listener_parent="$(ps -o ppid= -p "$listener_pid" | tr -d ' ')"
                if [[ "$listener_parent" != "$existing_pid" ]]; then
                    printf 'Port %s is not owned by the managed %s process.\n' \
                        "$service_port" "$service_name" >&2
                    return 1
                fi
            done <<< "$listener_pids"

            while IFS= read -r listener_pid; do
                [[ -n "$listener_pid" ]] && kill "$listener_pid" 2>/dev/null || true
            done <<< "$listener_pids"
            kill "$existing_pid" 2>/dev/null || true

            for ((attempt = 0; attempt < 10; attempt++)); do
                if ! nc -z 127.0.0.1 "$service_port"; then
                    break
                fi
                sleep 1
            done
            if nc -z 127.0.0.1 "$service_port"; then
                printf 'Could not stop the existing %s on port %s.\n' \
                    "$service_name" "$service_port" >&2
                return 1
            fi
            printf 'Stopped existing %s; starting updated code.\n' "$service_name"
        else
            printf 'Port %s is already in use; cannot start %s.\n' "$service_port" "$service_name" >&2
            return 1
        fi
    elif [[ -n "$existing_pid" ]]; then
        local child_pids
        child_pids="$(pgrep -P "$existing_pid" || true)"
        while IFS= read -r child_pid; do
            [[ -n "$child_pid" ]] && kill "$child_pid" 2>/dev/null || true
        done <<< "$child_pids"
        kill "$existing_pid" 2>/dev/null || true
    fi

    nohup "$@" >"$log_file" 2>&1 </dev/null &
    local service_pid=$!
    printf '%s\n' "$service_pid" > "$pid_file"

    for ((attempt = 0; attempt < 30; attempt++)); do
        if nc -z 127.0.0.1 "$service_port"; then
            printf 'Started %s on http://127.0.0.1:%s (PID %s). Log: %s\n' \
                "$service_name" "$service_port" "$service_pid" "$log_file"
            return 0
        fi
        if ! kill -0 "$service_pid" 2>/dev/null; then
            printf '%s exited before becoming ready. See %s\n' "$service_name" "$log_file" >&2
            return 1
        fi
        sleep 1
    done

    printf '%s did not become ready on port %s. See %s\n' \
        "$service_name" "$service_port" "$log_file" >&2
    return 1
}

start_service \
    "PULSE Chat API" \
    4000 \
    "$BACKEND_DIR/.chat-api.pid" \
    "$BACKEND_DIR/.chat-api.log" \
    uv run uvicorn app.main:app --host 127.0.0.1 --port 4000

start_service \
    "FastMCP" \
    8001 \
    "$BACKEND_DIR/.fastmcp.pid" \
    "$BACKEND_DIR/.fastmcp.log" \
    uv run fastmcp run mcp/server.py --transport http --host 127.0.0.1 --port 8001

printf 'PULSE Chat API: http://127.0.0.1:4000/docs\n'
printf 'FastMCP endpoint: http://127.0.0.1:8001/mcp\n'

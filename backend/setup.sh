#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FAKECLOUD_PID_FILE="$BACKEND_DIR/.fakecloud.pid"
FAKECLOUD_LOG_FILE="$BACKEND_DIR/.fakecloud.log"

cd "$BACKEND_DIR"

# Load local configuration without printing secrets. The file is git-ignored.
if [[ -f "$BACKEND_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND_DIR/.env"
    set +a
fi

export TF_VAR_groq_api_key="${GROQ_API_KEY:-}"
export TF_VAR_llm_base_url="${LLM_BASE_URL:-https://api.groq.com/openai/v1}"
export TF_VAR_llm_model="${LLM_MODEL:-openai/gpt-oss-20b}"

for required_command in docker fakecloud terraform nc psql aws; do
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

##### Initialize Terraform & Provision Base ECR / RDS Resources #####
cd "$BACKEND_DIR/terraform"
terraform init
terraform apply -auto-approve

wait_for_rds_endpoint() {
    local attempt
    for ((attempt = 0; attempt < 30; attempt++)); do
        if PGPASSWORD=testpassword psql \
            --host "$rds_host" \
            --port "$rds_port" \
            --username postgres \
            --dbname pulse \
            --no-psqlrc \
            -v ON_ERROR_STOP=1 \
            -tAc 'SELECT 1' >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

fakecloud_aws() {
    AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}" \
    AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}" \
    AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-ap-southeast-1}" \
        aws --endpoint-url http://127.0.0.1:4566 "$@"
}

##### Ensure Terraform's RDS endpoint has a live PostgreSQL listener #####
rds_endpoint="$(terraform output -raw rds_endpoint)"
rds_host="${rds_endpoint%:*}"
rds_port="${rds_endpoint##*:}"

if ! wait_for_rds_endpoint; then
    printf 'PostgreSQL is not reachable at %s:%s; restarting the local FakeCloud RDS instance.\n' \
        "$rds_host" "$rds_port" >&2

    rds_instance_id="$(
        fakecloud_aws rds describe-db-instances \
            --query 'DBInstances[0].DBInstanceIdentifier' \
            --output text \
            --no-cli-pager
    )"
    rds_instance_status="$(
        fakecloud_aws rds describe-db-instances \
            --query 'DBInstances[0].DBInstanceStatus' \
            --output text \
            --no-cli-pager
    )"
    if [[ -z "$rds_instance_id" || "$rds_instance_id" == "None" ||
        -z "$rds_instance_status" || "$rds_instance_status" == "None" ]]; then
        printf 'Could not find the local FakeCloud RDS instance to restart.\n' >&2
        exit 1
    fi

    if [[ "$rds_instance_status" != "stopped" ]]; then
        fakecloud_aws rds stop-db-instance \
            --db-instance-identifier "$rds_instance_id" \
            --no-cli-pager
    fi
    fakecloud_aws rds start-db-instance \
        --db-instance-identifier "$rds_instance_id" \
        --no-cli-pager
    fakecloud_aws rds wait db-instance-available \
        --db-instance-identifier "$rds_instance_id" \
        --no-cli-pager

    terraform apply -refresh-only -auto-approve
    rds_endpoint="$(terraform output -raw rds_endpoint)"
    rds_host="${rds_endpoint%:*}"
    rds_port="${rds_endpoint##*:}"

    if ! wait_for_rds_endpoint; then
        printf 'PostgreSQL did not become reachable at refreshed endpoint %s:%s.\n' \
            "$rds_host" "$rds_port" >&2
        exit 1
    fi
fi

##### Fetch remaining Terraform Outputs #####
ecr_repository_url="$(terraform output -raw ecr_repository_url)"
database_url="postgresql://postgres:testpassword@${rds_host}:${rds_port}/pulse"

# Update .env file
env_file="$BACKEND_DIR/.env"
env_temp_file="$(mktemp)"
if [[ -f "$env_file" ]]; then
    awk '!/^[[:space:]]*(export[[:space:]]+)?DATABASE_URL[[:space:]]*=/' "$env_file" > "$env_temp_file"
fi
printf 'DATABASE_URL=%s\n' "$database_url" >> "$env_temp_file"
mv "$env_temp_file" "$env_file"

run_sql_file() {
    PGPASSWORD=testpassword psql \
        --host "$rds_host" \
        --port "$rds_port" \
        --username postgres \
        --dbname pulse \
        -v ON_ERROR_STOP=1 \
        --file "$1"
}

##### Create tables before dependent tables #####
create_dir="$BACKEND_DIR/tables/create"
for table_script in create_campaign_chat_sessions.sql create_mock_campaign.sql create_mock_client.sql create_mock_campaign_advisor.sql create_campaign_email_send.sql create_mock_campaign_contact_event.sql; do
    if [[ -f "$create_dir/$table_script" ]]; then
        run_sql_file "$create_dir/$table_script"
    fi
done

for table_script in "$create_dir"/*.sql; do
    [[ -f "$table_script" ]] || continue
    case "${table_script##*/}" in
        create_campaign_chat_sessions.sql|create_mock_campaign.sql|create_mock_client.sql|create_mock_campaign_advisor.sql|create_campaign_email_send.sql|create_mock_campaign_contact_event.sql)
            continue
            ;;
    esac
    run_sql_file "$table_script"
done

##### Load mock data in foreign-key dependency order #####
mock_data_dir="$BACKEND_DIR/tables/mock_data"
for table_script in mock_campaign.sql mock_client.sql mock_campaign_advisor.sql mock_campaign_contact_events.sql; do
    if [[ -f "$mock_data_dir/$table_script" ]]; then
        run_sql_file "$mock_data_dir/$table_script"
    fi
done

for table_script in "$mock_data_dir"/*.sql; do
    [[ -f "$table_script" ]] || continue
    case "${table_script##*/}" in
        mock_campaign.sql|mock_client.sql|mock_campaign_advisor.sql|mock_campaign_contact_events.sql)
            continue
            ;;
    esac
    run_sql_file "$table_script"
done

if [[ "${DEPLOY_FAKECLOUD_ECS:-0}" != "1" ]]; then
    printf '\nLocal database provisioning complete.\n'
    printf 'DATABASE_URL was written to %s; chat, generated-draft and mock campaign tables are ready.\n' "$env_file"
    printf 'Start the application from the repository root with: make dev\n'
    printf 'Set DEPLOY_FAKECLOUD_ECS=1 to also build and deploy the emulated ECS image.\n'
    exit 0
fi

##### Build & Push Container Image to FakeCloud ECR #####
cd "$BACKEND_DIR"

# Ensure Dockerfile exists for app containerization
if [[ ! -f "Dockerfile" ]]; then
    cat <<'EOF' > Dockerfile
FROM python:3.11-slim

# Copy official uv binary from astral-sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation and use the project virtual environment
ENV UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Install locked project dependencies
COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY app /app/app
COPY mcp /app/mcp
COPY run_services.sh /app/run_services.sh
# Normalize Windows checkouts before running Bash in Linux.
RUN sed -i 's/\r$//' /app/run_services.sh

EXPOSE 4000 8001
CMD ["bash", "/app/run_services.sh"]
EOF
fi

printf 'Building Docker image for ECS...\n'
docker build -t pulse-chat-api:latest .

# Tag and push image to FakeCloud ECR
docker tag pulse-chat-api:latest "${ecr_repository_url}:latest"

printf 'Pushing image to FakeCloud ECR (%s)...\n' "${ecr_repository_url}"
docker push "${ecr_repository_url}:latest"

##### Force ECS Deployment Update #####
cd "$BACKEND_DIR/terraform"
terraform apply -auto-approve

printf '\n=======================================================\n'
printf 'ECS Deployment completed successfully!\n'
printf 'RDS Endpoint: %s\n' "$rds_endpoint"
printf 'ECR Image: %s:latest\n' "$ecr_repository_url"
printf 'ECS Service running task mapped to container ports 4000 and 8001\n'
printf '=======================================================\n'

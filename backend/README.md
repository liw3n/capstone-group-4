# PULSE Chat API

FastAPI backend for the PULSE chat popup. The service calls Groq through its
OpenAI-compatible API, discovers and invokes tools through FastMCP over HTTP,
and persists sessions and messages in PostgreSQL.

## Shared application setup

Follow the [team setup guide](../README.md#team-setup-and-development-workflow).
Run these from the repository root in macOS/Linux/WSL Bash, with all prerequisites
installed, including the standalone FakeCloud executable:

```bash
UV_PYTHON=3.11 make bootstrap
make doctor
```

Set your own `GROQ_API_KEY` in the ignored `backend/.env`, then:

```bash
make provision
make dev
```

`make provision` runs `setup.sh`, provisions the local database, writes its address
to `.env`, creates chat/mock tables and loads the synthetic seed SQL. The script
requires the standalone `fakecloud` executable, installed separately using the
[official installer](https://fakecloud.dev/docs/getting-started/install/):

```bash
curl -fsSL https://fakecloud.dev/install.sh | bash
command -v fakecloud
```

Install it before running `make provision`. The `localstack` Python dependency
does not provide this executable. `setup.sh` starts FakeCloud automatically;
keep Docker running so it can create the database container.

`make dev` starts FastAPI :4000, FastMCP :8001 `/mcp` and Vite :3000 together.
Present the feature through http://localhost:3000. `run_services.sh` is shared
startup infrastructure; discuss changes with the team before editing it. Do not
start a separate API Docker container alongside this workflow.

`DATABASE_URL` must be the generated address from provisioning. The old
`pulse-postgres:5432` value is for the previous direct Docker workflow. Keep the
example provider/model settings and `MCP_SERVER_URL=http://127.0.0.1:8001/mcp`
unless an intentional configuration change is agreed. Never commit `.env` or keys.

Shell scripts use LF line endings. The Dockerfile normalizes line endings for
optional image builds. The emulated ECS path is optional; set
`DEPLOY_FAKECLOUD_ECS=1` when running `make provision` to exercise it. It is not
required for `make dev` or the interim presentation.

## System architecture

[Architecture.svg](docs/Architecture.svg) shows the complete current system:
React CRM and PULSE chat, the Vite proxy, FastAPI, LLM orchestration, FastMCP,
Groq and PostgreSQL. It distinguishes browser-only CRM state from backend
persistence and labels the team Terraform/FakeCloud provisioning workflow,
optional ECS and planned company CRM integration. The existing PNG is an older export.

## Endpoints

- `GET /health`
- `GET /chat/sessions?fa_id=<id>`
- `POST /chat/new?fa_id=<id>`
- `GET /chat/history?session_id=<id>`
- `POST /chat/query`

See `docs/api_contract.md` for request and response details.

## Tools

The FastMCP server registers tools in `mcp/server.py`; the API retrieves their
schemas and calls them through `app/tools/mcp_registry.py`. Configure
`MCP_SERVER_URL` to the server's Streamable HTTP `/mcp` endpoint; it defaults to
`http://127.0.0.1:8001/mcp` when the API and MCP server run on the same host.

The registered tools include `recommend_clients_for_campaign` and
`campaign_follow_up`. Campaign matching and scoped data access live in
`app/campaigns/`; shared follow-up handlers live in
`app/tools/implementations.py`. Follow-up handlers query the mock engagement
table and currently return simulated client profile and portfolio data.

The MCP server serves `http://127.0.0.1:8001/mcp` using Streamable HTTP. Use
`make dev` or `make backend-dev` from the repository root to start the shared
backend processes; a standalone tool demo program is not required.

## Tests

```bash
uv run pytest
```

The automated tests mock the model provider and do not require an API key or make
network calls.


## Synthetic campaign recommendations

PULSE can recommend synthetic clients for the selected seeded campaign using
`recommend_clients_for_campaign`. The model sees campaign ID and limit only;
the API supplies request-scoped adviser/tenant identity via MCP metadata.

The repository reads synthetic PostgreSQL tables created and seeded by
`make provision`. Verify both campaigns in the shared frontend after `make dev`.
The matching logic does not call Groq; automated unit/integration tests can verify
it independently, without a separate demo script.

See [prototype assumptions, SQL and frontend verification](docs/campaign_recommendations.md).

# PULSE Chat API

FastAPI backend for the PULSE chat popup. The service calls Groq through its
OpenAI-compatible API, discovers and invokes tools through FastMCP over HTTP,
and persists sessions and messages in PostgreSQL.

## Complete application setup

Follow the [teammate Docker setup guide](../README.md#teammate-setup-and-running-the-whole-application-windows--docker)
for database creation, shared mock SQL, `.env`, API/MCP startup, frontend startup,
verification and daily restarts. That workflow needs Docker and Node.js;
FakeCloud/Terraform is an optional alternative below.

## Configuration

Copy `.env.example` to `.env` and set a newly generated Groq key:

```bash
cp .env.example .env
```

Required settings:

- `DATABASE_URL`
- `GROQ_API_KEY`

The provider URL, model, timeout, history limit, and maximum tool rounds can also
be changed through the `LLM_*` values shown in `.env.example`. Never commit `.env`.

## Local setup

Install `uv`, FakeCloud, Terraform, PostgreSQL tools, and Docker, then run:

```bash
uv sync --dev
./setup.sh
uv run bash run_services.sh
```

`setup.sh` starts FakeCloud, provisions the local AWS resources, writes the
generated PostgreSQL connection to the ignored `.env`, creates chat and synthetic
recommendation tables, and seeds two demo campaigns and 14 mock clients. That
is everything required by the Vite/FastAPI development workflow.

Shell scripts use LF line endings, enforced by `.gitattributes`. The Docker
build also normalizes `run_services.sh` so Windows checkouts work in Linux.
After pulling a startup-script fix, rebuild the API image before running it.

The API listens on port `4000`; the FastMCP Streamable HTTP endpoint listens on
port `8001` at `/mcp`. `MCP_SERVER_URL` can override the API's MCP endpoint.
`make dev` and `make backend-dev` start both processes.

The emulated ECS image path is optional:

```bash
DEPLOY_FAKECLOUD_ECS=1 ./setup.sh
```

Depending on the Docker runtime, pushing to FakeCloud's HTTP ECR endpoint may
require local insecure-registry configuration. It is not required for `make dev`.

For native Python development with an existing PostgreSQL instance, run the table
SQL manually and start both Uvicorn and MCP without `setup.sh`. Use the
[manual commands](../README.md#manual-development-commands); Uvicorn alone cannot
execute MCP tools.

## System architecture

[Architecture.svg](docs/Architecture.svg) shows the complete current system:
React CRM and PULSE chat, the Vite proxy, FastAPI, LLM orchestration, FastMCP,
Groq and PostgreSQL. It distinguishes browser-only CRM state from backend
persistence and labels the optional Terraform/FakeCloud ECR/ECS/RDS setup and
planned company CRM integration. The existing PNG is an older export.

## Endpoints

- `GET /health`
- `GET /chat/sessions?fa_id=<id>`
- `POST /chat/new?fa_id=<id>`
- `GET /chat/history?session_id=<id>`
- `POST /chat/query`

See `docs/api_contract.md` for request and response details.

## Tools

The FastMCP server registers tools in `mcp/server.py`; the API retrieves their
schemas and calls them through `app/tools/mcp_registry.py`. Business logic lives
in `app/tools/implementations.py`. `search_database` remains an explicit
placeholder; replace its implementation before using it with production
campaign data.

Run only the MCP server from this directory with:

```bash
uv run python mcp/server.py
```

It serves `http://127.0.0.1:8001/mcp` using Streamable HTTP.

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

The repository reads synthetic PostgreSQL tables. Create and seed them, configure
`DATABASE_URL`, then inspect results without Groq:

```powershell
uv run python -B -m app.campaigns.demo camp-1
uv run python -B -m app.campaigns.demo camp-2
```

For the local Docker database, Windows processes connect to `127.0.0.1:55432`;
API containers on `pulse-dev` connect to `pulse-postgres:5432`.
See [database setup, prototype assumptions and tests](docs/campaign_recommendations.md).

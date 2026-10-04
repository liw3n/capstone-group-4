# PULSE Chat API

FastAPI backend for the PULSE chat popup. The service calls Groq through its
OpenAI-compatible API, discovers and invokes tools through FastMCP over HTTP,
and persists sessions and messages in PostgreSQL.

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
bash run_services.sh
```

`setup.sh` starts FakeCloud, provisions the local AWS resources, writes the
generated PostgreSQL connection to the ignored `.env`, and creates both chat
tables. That is everything required by the Vite/FastAPI development workflow.

The API listens on port `4000`; the FastMCP Streamable HTTP endpoint listens on
port `8001` at `/mcp`. `MCP_SERVER_URL` can override the API's MCP endpoint.
`make dev` and `make backend-dev` start both processes.

The emulated ECS image path is optional:

```bash
DEPLOY_FAKECLOUD_ECS=1 ./setup.sh
```

Depending on the Docker runtime, pushing to FakeCloud's HTTP ECR endpoint may
require local insecure-registry configuration. It is not required for `make dev`.

For API-only development with an existing PostgreSQL instance, run the table SQL
manually and start Uvicorn without `setup.sh`.

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

# PULSE Chat API

FastAPI backend for the PULSE chat popup. The service calls Groq through its
OpenAI-compatible API, supports local function tools, and persists sessions and
messages in PostgreSQL.

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
uv run uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```

`setup.sh` starts FakeCloud, provisions the local AWS resources, writes the
generated PostgreSQL connection to the ignored `.env`, and creates both chat
tables. That is everything required by the Vite/FastAPI development workflow.

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

Tool definitions live in `app/tools/registry.py`, and their business logic lives
in `app/tools/implementations.py`. The same implementations are exposed by the
FastMCP server. `search_database` remains an explicit placeholder; replace its
implementation before using it with production campaign data.

Run the MCP server from this directory with:

```bash
uv run python mcp/server.py
```

## Tests

```bash
uv run pytest
```

The automated tests mock the model provider and do not require an API key or make
network calls.

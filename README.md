# PULSE CRM

BT4103 Capstone Project (Team 4). The repository combines a MyWealth-style CRM
frontend with a FastAPI chat service backed by PostgreSQL and an
OpenAI-compatible LLM provider.

## Repository layout

- `frontend/`: React 19, TypeScript, Vite and Tailwind CRM interface. The PULSE
  assistant uses the backend `/api/chat/...` routes; other CRM modules currently
  use deterministic seed data.
- `backend/`: FastAPI application, PostgreSQL chat persistence, LLM/tool
  orchestration, a FastMCP entry point, and local FakeCloud/Terraform setup.
- `gwm_api/`: handling guidance for locally supplied, git-ignored company
  OpenAPI documents. These specifications are not runnable services.

## Local development

The quickest workflow uses the root Makefile. First install Node.js 20 and `uv`,
then run:

```bash
make bootstrap
# Set GROQ_API_KEY and DATABASE_URL in backend/.env.
make provision  # first run only, unless PostgreSQL is already prepared
make dev
```

Open http://localhost:3000. `make dev` runs FastAPI on port `4000` and Vite on
port `3000`; pressing Ctrl-C stops both. Use `make help` to see individual
service, testing, build, and verification targets.

The equivalent manual commands are below.

Configure and start the backend first:

```bash
cd backend
cp .env.example .env
uv sync --dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```

The configured PostgreSQL database must contain the tables in
`backend/tables/create_campaign_chat_sessions.sql`.

`make provision` starts the local FakeCloud resources, writes the generated
PostgreSQL URL to the ignored `backend/.env`, and initializes the chat tables.
It does not build the optional emulated ECS image unless
`DEPLOY_FAKECLOUD_ECS=1` is set.

In a second terminal, start the frontend with Node.js 20 LTS:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. The Vite development server forwards `/api` to the
backend on port `4000`.

## Verification

```bash
cd frontend && npm run lint && npm run build
cd ../backend && uv run pytest
cd .. && python3 -m compileall -q backend/app backend/mcp
bash -n backend/setup.sh
terraform -chdir=backend/terraform fmt -check
```

See `frontend/README.md`, `backend/README.md`, and
`backend/docs/api_contract.md` for component-specific details.

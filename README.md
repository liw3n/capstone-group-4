# PULSE CRM

BT4103 Capstone Project (Team 4). PULSE combines a MyWealth-style adviser CRM
with a persistent AI assistant backed by FastAPI, PostgreSQL, and Groq's
OpenAI-compatible API.

## Architecture

```text
Browser
  -> React + Vite (:3000)
       -> /api development proxy -> FastAPI (:4000)
            -> PostgreSQL (chat + synthetic campaign/client storage)
            -> Groq (HTTPS, AI responses and tool calls)
            -> FastMCP HTTP (:8001/mcp) -> scoped matching -> PostgreSQL
```

![PULSE system architecture](backend/docs/Architecture.svg)

[Open the full system diagram](backend/docs/Architecture.svg). The PNG is an older export.

- `frontend/` contains the React 19, TypeScript, Vite, and Tailwind CRM. The
  floating PULSE panel calls `/api/chat/...`; the other CRM modules currently
  use synthetic seed data and React state.
- `backend/` contains the FastAPI routes, PostgreSQL data access, LLM client,
  bounded tool orchestration, shared tool implementations, FastMCP prototype,
  SQL, tests, and local FakeCloud/Terraform configuration.
- `backend/app/tools/` discovers and invokes FastMCP tools over HTTP. The
  API and MCP server run as separate processes in the same API container.
  The client recommendation tool reads the synthetic PostgreSQL tables.
- `docs/` and `gwm_api/` contain handling guidance for locally supplied company
  reference material. Confidential source files are intentionally git-ignored.

Chat sessions and successful user/assistant exchanges are stored locally in
PostgreSQL tables `campaign_chat_sessions` and `campaign_chat_messages`.
Synthetic campaign criteria, adviser assignments and client profiles live in
`mock_campaign`, `mock_campaign_advisor` and `mock_client`.

## Teammate setup and running the whole application (Windows / Docker)

This is the local demo setup used by the team. Docker runs PostgreSQL in one
container and **FastAPI plus the MCP server together** in another. The frontend
runs through npm on your computer. Starting only MCP and the frontend is not
enough: the frontend calls FastAPI, which manages chat and invokes MCP tools.

### 1. Install the prerequisites and get the repository

Install Git, Docker Desktop, and Node.js with npm. Use Node.js **22.12 or newer**
from a supported release line; the locked React/Vite plugin requires at least
22.12 on Node 22. You do not need a separate Python installation, uv, Terraform,
FakeCloud, or PostgreSQL installation for this Docker workflow.

Clone the team's repository, or pull the latest changes in your existing checkout.
Make sure your checkout includes the recommendation feature and SQL seed files.
Open Docker Desktop and wait until the engine is running. In **PowerShell**:

```powershell
docker info
node --version
npm --version
```

If PowerShell blocks `npm.ps1`, use `npm.cmd` wherever this guide says `npm`.
If Docker reports missing virtualization support, enable firmware virtualization
and WSL 2 / Virtual Machine Platform as needed, then restart Windows before
continuing.

### 2. Create and start the PostgreSQL database

Replace the example folder below with **your own repository location**. Run from
`backend/` in PowerShell:

```powershell
cd "C:\path\to\capstone-group-4\backend"
docker network create pulse-dev
docker run -d --name pulse-postgres --network pulse-dev -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=testpassword -e POSTGRES_DB=pulse -v pulse-pgdata:/var/lib/postgresql/data postgres:15
```

The network connects the API and database containers. The named volume
`pulse-pgdata` keeps database records when a container stops. `testpassword` is
an example password for this local synthetic demo; if you change it, use the same
password in the database settings in step 4.

If Docker says the network already exists, continue. If the database container
already exists, use `docker start pulse-postgres` instead of creating it again.
Changing the password argument does not change a database already initialized
in the volume.

Check readiness:

```powershell
docker exec pulse-postgres pg_isready -U postgres -d pulse
```

Wait a few seconds and repeat until it reports **accepting connections**.

### 3. Create the tables and load the shared mock data

Still in `backend/`, run these commands in order:

```powershell
docker cp .\tables\create_campaign_chat_sessions.sql pulse-postgres:/tmp/chat.sql
docker exec pulse-postgres psql -U postgres -d pulse -v ON_ERROR_STOP=1 -f /tmp/chat.sql

docker cp .\tables\create_mock_campaign_tables.sql pulse-postgres:/tmp/mock-tables.sql
docker exec pulse-postgres psql -U postgres -d pulse -v ON_ERROR_STOP=1 -f /tmp/mock-tables.sql

docker cp .\tables\seed_mock_campaign_data.sql pulse-postgres:/tmp/mock-seed.sql
docker exec pulse-postgres psql -U postgres -d pulse -v ON_ERROR_STOP=1 -f /tmp/mock-seed.sql
```

This creates chat storage and the mock campaign, adviser-access and client tables.
The checked-in seed SQL supplies the same two demo campaigns and 14 synthetic
clients to every teammate's **own local database**. To share new mock records, add them to the
seed SQL and share that change through Git; edits made only inside your database
remain local.

These scripts can be rerun. Existing seed records are preserved rather than
reset, so reseeding does not overwrite someone's local edits. Stop if any SQL
command reports an error before proceeding to the application.

### 4. Configure the backend environment

Create `.env` only if it does not already exist, then open it in Notepad:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
notepad .env
```

In **Notepad**, set these lines, keeping the other example settings:

```dotenv
DATABASE_URL=postgresql://postgres:testpassword@pulse-postgres:5432/pulse
GROQ_API_KEY=your_actual_groq_api_key
MCP_SERVER_URL=http://127.0.0.1:8001/mcp
```

Replace `your_actual_groq_api_key` with your own Groq API key, press **Ctrl+S**,
and close Notepad. Do not paste these settings as PowerShell commands. Never
commit `.env` or put the key in frontend configuration. A Groq key is needed for
AI chat; creating tables and matching clients directly do not need one.

`pulse-postgres:5432` is the database address **inside the Docker network**.
`127.0.0.1:55432` is its address for tools running directly on Windows. MCP uses
`127.0.0.1:8001` because it runs inside the same container as FastAPI.

### 5. Build and start the backend

Still in `backend/`:

```powershell
docker build -t pulse-chat-api .
docker run --rm --name pulse-api --network pulse-dev --env-file .env -p 127.0.0.1:4000:4000 pulse-chat-api
```

Keep this terminal open. The container starts **both** FastMCP on port 8001 and
FastAPI on port 4000. You do not run `python mcp/server.py` separately for this
setup. The first image build downloads Python dependencies and can take time.

In another PowerShell window, check the API:

```powershell
Invoke-RestMethod http://localhost:4000/health
```

Expect `status` to be `ok` and `llm_configured` to be `True`. This checks API
startup and the presence of a provider key; it does not verify that the key is
valid or that the database works. The campaign/chat check below covers the full
application path.

### 6. Install and start the frontend

In the second PowerShell window, replace the folder with your checkout location:

```powershell
cd "C:\path\to\capstone-group-4\frontend"
npm ci
npm run dev
```

Keep this terminal open too. Open **http://localhost:3000**. No frontend `.env`
is needed for this setup: Vite proxies `/api` requests to `localhost:4000`.

### 7. Check the recommendation feature

Choose **Financial Advisor** (the Steven Raynaldi demo account), open
**Campaigns**, and select **Legacy Protection Refresh**. Open PULSE, click
**Ask for recommended clients**, then send the question. You should get four
matches: **Demo Clients A, B, C and L**, two incomplete profiles, and six clients
excluded by the rules. **First Home Starter Bundle** should return three matches:
**F, G and H**, two incomplete profiles, and seven excluded clients.

The seeded demo uses a fixed date of **2026-08-26**, so these counts do not change
with today's date. These are matches from the separate PostgreSQL mock dataset;
the frontend CRM's 75 contacts and browser-created campaigns are independent.
Only the two seeded campaign IDs are available to this backend prototype.

To inspect matching without an AI call while the API container is running,
use another terminal:

```powershell
docker exec pulse-api python -B -m app.campaigns.demo camp-1
docker exec pulse-api python -B -m app.campaigns.demo camp-2
```

### Daily startup, stopping, and updating

After the first-time setup, open Docker Desktop. In a backend terminal:

```powershell
cd "C:\path\to\capstone-group-4\backend"
docker start pulse-postgres
docker exec pulse-postgres pg_isready -U postgres -d pulse
docker run --rm --name pulse-api --network pulse-dev --env-file .env -p 127.0.0.1:4000:4000 pulse-chat-api
```

Wait for the database readiness check to succeed before starting the API.
In a separate frontend terminal:

```powershell
cd "C:\path\to\capstone-group-4\frontend"
npm run dev
```

You do not recreate the network, database, or tables on every startup. Press
**Ctrl+C** in each application terminal to stop the API/MCP and frontend.
`--rm` removes the stopped API container; the image remains for the next run.
To stop the database without deleting its data, run `docker stop pulse-postgres`.
If `pulse-api` is already running in the background, use it as-is, or stop it with
`docker stop pulse-api` before starting another container with the same name.

After pulling backend changes, stop the API, run `docker build -t pulse-chat-api .`
from `backend/`, then run the API command again. After frontend dependency changes,
stop Vite, run `npm ci` from `frontend/`, then restart `npm run dev`. Apply new SQL
scripts when a change calls for them. Restart the API after editing `.env` because
Docker reads the environment at container creation. Do not run FakeCloud's
`setup.sh` against this setup: it provisions a different database and rewrites
the database configuration.

### Docker setup troubleshooting

- **Database unavailable / HTTP 503:** check `docker ps` and database readiness,
  confirm all three SQL files ran, and check the `.env` hostname is
  `pulse-postgres`, not `localhost`, for the API container.
- **`pulse-api` name already in use:** it may already be running. Use that instance
  or stop it before running the startup command again.
- **`invalid option name ... pipefail`:** pull the startup-script fix and rebuild
  the API image. The Dockerfile normalizes Windows line endings before startup.
- **Port 3000, 4000 or 55432 already in use:** stop the conflicting local service
  before starting this setup. Use the Vite URL printed in its terminal; a different
  API/database port also requires updating the corresponding configuration.
- **Groq errors:** confirm the key was replaced and restart the API after changing
  `.env`. `llm_configured=True` only checks that a value exists. Provider responses
  may also be affected by authentication, connectivity or rate limits.

## Optional macOS / FakeCloud workflow

The following workflow is an alternative for development with locally installed
Python services and emulated AWS infrastructure. It is not required for the
Docker setup above; use one database setup at a time.

### Additional prerequisites

For this alternative, use macOS with the following installed:

- Docker Desktop (the Docker CLI alone is not sufficient)
- Node.js 22.12 or newer and npm
- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for Python environments and dependencies
- FakeCloud
- Terraform
- PostgreSQL command-line tools (`psql`)
- AWS CLI
- Netcat (`nc`, included with macOS)
- Make (included with Xcode Command Line Tools)

One Homebrew setup is:

```bash
brew install node@22 uv fakecloud awscli libpq
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

`node@22` and `libpq` may be keg-only. Follow the PATH instructions printed by
Homebrew so that both `node` and `psql` are found in a new terminal.

Open Docker Desktop and wait for its engine to become ready:

```bash
open -a Docker
docker info
```

### First-time FakeCloud setup

Run these commands from the repository root, not from `backend/`:

```bash
make bootstrap
make doctor
```

`make bootstrap` creates the Python virtual environment with `uv`, installs the
locked backend and frontend dependencies, and creates `backend/.env` from the
example if it does not already exist.

Add your own Groq key to `backend/.env`:

```dotenv
GROQ_API_KEY=your-key-here
```

Never commit or share `backend/.env`. Provider credentials stay in the backend;
do not put them in a `VITE_*` variable because Vite exposes those values to the
browser. `make provision` will replace the example `DATABASE_URL` with the
generated local PostgreSQL address.

With Docker Desktop running, provision the local database:

```bash
make provision
```

Then start both applications:

```bash
make dev
```

Open http://localhost:3000, choose the Financial Advisor role, and click the
floating PULSE button. Press `Ctrl-C` in the terminal running `make dev` to stop
both development servers.

### What `setup.sh` does

`make provision` runs `backend/setup.sh`. The script requires these commands to
be on PATH:

```text
docker  fakecloud  terraform  nc  psql  aws
```

The normal setup path:

1. Loads the ignored `backend/.env` without printing its secrets.
2. Starts FakeCloud on `127.0.0.1:4566` if it is not already running.
3. Runs `terraform init` and `terraform apply` against FakeCloud's local AWS
   endpoints.
4. Creates a local PostgreSQL container and reads its generated host port.
5. Writes the generated `DATABASE_URL` back to `backend/.env`.
6. Applies the chat and mock campaign table SQL, then seeds the demo campaigns
   and clients with `psql`.
7. Stops after reporting that the local demo database is ready.

The SQL is idempotent, so provisioning can be rerun when the local database has
been removed or recreated. This is development infrastructure: deleting the
Docker/FakeCloud database may delete locally stored chats.

#### Optional emulated ECS deployment

The frontend does not need an ECS container. `make dev` runs FastAPI directly
from the `uv` environment. To additionally exercise the emulated container
deployment path:

```bash
cd backend
DEPLOY_FAKECLOUD_ECS=1 ./setup.sh
```

This optional path builds the backend image, pushes it to FakeCloud's emulated
ECR, and reapplies Terraform. Some Docker runtimes require extra insecure-
registry configuration for FakeCloud's local HTTP registry. Do not use this
path for routine frontend/backend development.

## Make commands

| Command | Purpose |
| --- | --- |
| `make help` | List the supported project commands. |
| `make doctor` | Check Node, npm, `uv`, installed dependencies, and `.env`. |
| `make configure` | Create `backend/.env` without overwriting an existing one. |
| `make install` | Install locked backend and frontend dependencies. |
| `make bootstrap` | Run installation and create the local environment file. |
| `make provision` | Provision FakeCloud resources and initialize PostgreSQL. |
| `make dev` | Run FastAPI `:4000`, FastMCP `:8001` and Vite `:3000`. |
| `make backend-dev` | Run FastAPI and FastMCP together. |
| `make frontend-dev` | Run only Vite. |
| `make test` | Run backend tests and the frontend TypeScript check. |
| `make frontend-build` | Create the production frontend bundle. |
| `make verify` | Run tests, build, Python compilation, shell validation, and Terraform formatting checks. |

## Python and `uv`

The backend dependency sources of truth are `backend/pyproject.toml` and
`backend/uv.lock`. Do not manually populate the environment with `pip`.

Run backend commands from `backend/` through `uv`:

```bash
uv sync --dev
uv run pytest
uv run uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
uv run python mcp/server.py
```

The MCP command starts the HTTP tool server on `:8001/mcp`. It must run
alongside FastAPI for tool-backed chat. `make dev` starts both for you.

## Manual development commands

For native Python development with an already configured database, run FastAPI
in one terminal and MCP in another. Do not use these commands while the Docker
API container already owns port 4000. For the Docker database, native Python
uses `127.0.0.1:55432` in `DATABASE_URL`, rather than `pulse-postgres:5432`.

Start FastAPI from the repository root in the first terminal:

```bash
cd backend
uv sync --dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```

Start MCP from the repository root in the second terminal:

```bash
cd backend
uv run python mcp/server.py
```

Start the frontend from the repository root in a third terminal:

```bash
cd frontend
npm ci
npm run dev
```

Vite forwards `/api` requests to `http://localhost:4000`. For a separately
hosted backend, set `VITE_API_BASE_URL` to its public origin; never put backend
credentials in the frontend environment.

## Verification

The complete project check is:

```bash
make verify
```

Equivalent component commands are:

```bash
cd backend
uv run pytest

cd ../frontend
npm run lint
npm run build

cd ..
python3 -m compileall -q backend/app backend/mcp
bash -n backend/setup.sh
terraform -chdir=backend/terraform fmt -check
```

Backend tests mock Groq and do not make provider network calls. Focused chat
rendering tests run with `npm run test:chat` from `frontend/`; `npm run lint` performs strict TypeScript checking. There is
no complete frontend component or end-to-end suite.

## Troubleshooting

### `Required command not found`

Install the command named by `setup.sh`, open a new terminal, and confirm it is
on PATH with `command -v <name>`. In particular, Homebrew's `libpq` installation
may require a PATH update before `psql` is visible.

### Docker connection errors

Open Docker Desktop, wait for it to report that the engine is running, then
confirm:

```bash
docker info
```

### PULSE reports that chat storage is unavailable

Check that the local database container is running:

```bash
docker ps
```

For the Docker setup, follow the database checks in the teammate setup section
above and restart the API. For the optional FakeCloud setup, reprovision and
restart the application:

```bash
make provision
make dev
```

`setup.sh` writes a generated port into `backend/.env`, so restart FastAPI after
reprovisioning to reload `DATABASE_URL`.

### Groq configuration or provider errors

Check the backend health response:

```bash
curl http://localhost:4000/health
```

`llm_configured` should be `true`. A `429` means the provider rate-limited the
request; `502` indicates provider authentication/connectivity/response failure;
`504` indicates a provider timeout.

### Ports already in use

Check which process owns the development ports:

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:4000 -sTCP:LISTEN
```

## Current limitations

- Adviser role selection and `fa_id` are prototype mechanisms, not real
  authentication or authorization.
- The campaign/database search tool is still a labelled placeholder; real CRM
  campaign and contact data are not yet available to Groq.
- Most CRM state is synthetic frontend data and resets on refresh. PULSE
  chat sessions, successful exchanges and the separate recommendation dataset
  are persisted in PostgreSQL. Browser-created campaigns are not synced to it.
- FakeCloud/Terraform is a local demonstration stack, not a production AWS
  design.

See `frontend/README.md`, `backend/README.md`,
`backend/docs/api_contract.md`, and the nearest `AGENTS.md` for more detail.

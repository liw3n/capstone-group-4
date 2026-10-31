# PULSE Demo Deployment Implementation Plan

Status: Proposed

This plan describes how to package and host PULSE as a limited capstone demo
that invited testers can access with shared credentials. The target is a
repeatable, same-origin deployment with synthetic data, simulated email
delivery, managed PostgreSQL, and no connection to company systems. It is not a
production authentication, authorisation, financial-advice, or infrastructure
design.

The recommended target is one public Docker web service and one managed
PostgreSQL database in the same Singapore region. The container serves the
React application and FastAPI API on one public port, while FastMCP remains an
internal process on port `8001`. A shared HTTP Basic Authentication gate limits
access to invited testers before they reach the existing prototype role
selector.

```text
Tester
  | HTTPS and shared demo credentials
  v
Docker web service
  |-- React production build
  |-- FastAPI on the platform-supplied port
  `-- FastMCP on 127.0.0.1:8001
          |
          |-- Managed PostgreSQL
          `-- Groq API
```

The work is divided into independently testable stages. Each stage should keep
the existing local Make workflow operational and should be suitable for a
separate pull request.

## Stage 0 Confirm the deployment scope

Agree on the following boundaries before changing code:

- Use Render in its Singapore region for the first hosted demo.
- Deploy one public Docker web service and one managed PostgreSQL database.
- Package React, FastAPI, and FastMCP in the application image.
- Expose only the FastAPI-facing public port; keep FastMCP on
  `127.0.0.1:8001`.
- Protect the complete application with shared HTTP Basic Authentication.
- Keep the existing Financial Adviser and Marketing role selector after the
  authentication gate.
- Use only checked-in synthetic data and keep `EMAIL_DELIVERY_MODE=mock`.
- Do not configure a live GWM endpoint or use company credentials.
- Run one application instance initially because the current synchronous
  persistence and startup design has not been evaluated for horizontal
  scaling.
- Set an expiry date for the environment and rotate or remove its credentials
  after testing.

### Deliverable

Record the agreed provider, region, environment owner, expected lifetime, and
demo limitations in this document or a short architecture decision record.

### Exit criteria

The team agrees that the environment is a synthetic capstone demonstration and
not a production system or security boundary.

## Stage 1 Build the complete application container

The current `backend/Dockerfile` packages FastAPI and FastMCP but not the React
frontend. Add a root-level multi-stage Dockerfile that produces one runnable
application image.

### Implementation

1. Add a Node 20 build stage that copies the frontend manifest and lockfile,
   runs `npm ci`, copies the frontend source, and runs `npm run build`.
2. Add a Python 3.11 dependency stage that installs the locked backend runtime
   dependencies with `uv sync --frozen --no-dev`.
3. Copy the backend application, MCP server, startup script, frontend production
   bundle, and deployment database scripts into the final image.
4. Serve the frontend through FastAPI after all API routes are registered. Add
   an SPA fallback to `index.html` without intercepting `/api/...`, `/chat/...`,
   `/campaigns/...`, or other backend routes.
5. Update `backend/run_services.sh` to bind FastAPI to `${PORT:-4000}` while
   preserving port `4000` for local development.
6. Continue starting FastMCP on internal port `8001` and use
   `MCP_SERVER_URL=http://127.0.0.1:8001/mcp`.
7. Run the final image as a non-root user and preserve graceful shutdown of both
   Python processes.
8. Add a root `.dockerignore` that excludes Git metadata, virtual environments,
   `node_modules`, build outputs, logs, state, `.env`, Terraform state, and
   caches.

Only the public application port should be documented for hosted access. Port
`8001` is an internal process boundary within the prototype container.

### Verification

```bash
docker build --platform linux/amd64 -t pulse-demo .
docker run --env-file backend/.env -p 4000:4000 pulse-demo
```

Verify that the React application loads at `/`, frontend API requests use the
same origin, page refreshes do not return `404`, FastMCP is ready before tool
requests are accepted, and both direct and `/api` route forms continue to work.

### Exit criteria

The complete application works through one container, one browser origin, and
one public port.

## Stage 2 Add a hosted database workflow

Do not run `backend/setup.sh` in the hosted environment. That script is designed
for local FakeCloud, Terraform, and a generated local `.env` file.

### Implementation

Create the following deployment commands:

```text
deploy/
  migrate.sh
  seed-demo.sh
  reset-demo.sh
```

`migrate.sh` should:

- Require `DATABASE_URL` without printing it.
- Apply schema files in explicit foreign-key dependency order.
- Stop on the first SQL error.
- Be safe to execute repeatedly.
- Avoid starting FakeCloud, applying Terraform, or changing `.env`.

`seed-demo.sh` should:

- Load only checked-in synthetic records.
- Be safe to retry.
- Remain separate from migration so ordinary deployments do not unexpectedly
  restore deleted or modified demo rows.
- State clearly that it performs a synthetic demo-data operation.

`reset-demo.sh` is optional. If added, it must require an explicit confirmation
argument, validate the target database, and document that the operation destroys
hosted demo state.

Add a local `docker-compose.yml` with the application and PostgreSQL, health
checks, a named PostgreSQL volume, and non-secret local defaults. A typical
local sequence should be:

```bash
docker compose up -d postgres
docker compose run --rm app ./deploy/migrate.sh
docker compose run --rm app ./deploy/seed-demo.sh
docker compose up app
```

The first hosted release may continue using the current idempotent SQL. A real
migration framework should be introduced before incompatible schema changes or
production use.

### Verification

- Apply migrations twice to a fresh PostgreSQL database.
- Apply the seed operation twice.
- Restart the application and confirm that data persists.
- Confirm that adviser and tenant scope checks still apply.
- Confirm that the database contains only synthetic data.

### Exit criteria

A fresh PostgreSQL database can be prepared without FakeCloud or Terraform, and
schema migration is separate from demo-data seeding.

## Stage 3 Protect the deployment with demo credentials

Add shared HTTP Basic Authentication as a temporary access gate for invited
testers. This gate limits public access but does not replace the prototype's
caller-supplied adviser identity with production authentication.

### Implementation

Add environment-backed settings:

```text
DEMO_AUTH_ENABLED
DEMO_AUTH_USERNAME
DEMO_AUTH_PASSWORD
```

Add FastAPI middleware that:

- Protects frontend assets and all API routes.
- Returns `401` with `WWW-Authenticate` when credentials are absent or invalid.
- Uses constant-time comparisons.
- Never logs the authorization header or credential values.
- Allows authentication to be disabled for normal local development.
- Exempts only the minimal liveness endpoint required by the hosting platform.

Recommended configuration:

```text
Local development: DEMO_AUTH_ENABLED=false
Hosted demo:      DEMO_AUTH_ENABLED=true
```

Do not place credentials in source code, frontend variables, Docker build
arguments, screenshots, or presentations. The existing role selector should
remain and should continue to state that it selects a prototype role rather
than representing an authenticated account.

### Verification

- Missing and incorrect credentials return `401`.
- Correct credentials allow access to the frontend and API.
- Authentication covers chat, contact, campaign, and draft-review routes.
- Credentials are absent from the browser bundle and application logs.
- Local authentication-disabled mode continues to work.

### Exit criteria

Someone who knows only the public URL cannot use the application or its API.

## Stage 4 Harden configuration and health checks

### Implementation

1. Remove wildcard CORS for the same-origin deployment. If CORS is still
   required, allow only the deployed frontend origin.
2. Add `GET /live` as a minimal unauthenticated process-liveness endpoint.
3. Add `GET /ready` as a dependency-readiness endpoint that performs a minimal
   PostgreSQL query and checks that FastMCP is reachable.
4. Return `503` from readiness checks when a required dependency is unavailable,
   without returning connection strings, internal exception text, or secrets.
5. Configure a stable `PULSE_CAMPAIGN_RETRIEVAL_SECRET` so outstanding reference
   tokens do not become invalid merely because the container restarts.
6. Add redacted startup logging for the application version, configuration
   presence, and MCP readiness. Log whether a value is configured, never the
   value itself.

Hosted runtime variables should include:

```text
DATABASE_URL
GROQ_API_KEY
LLM_BASE_URL
LLM_MODEL
MCP_SERVER_URL
PULSE_CAMPAIGN_RETRIEVAL_SECRET
EMAIL_DELIVERY_MODE
DEMO_AUTH_ENABLED
DEMO_AUTH_USERNAME
DEMO_AUTH_PASSWORD
```

Keep `EMAIL_DELIVERY_MODE=mock`. Do not configure the GWM email variables for
the public capstone demo.

### Verification

- Test startup with each required variable absent.
- Simulate unavailable PostgreSQL and unavailable FastMCP.
- Confirm `/live` reports the process state while `/ready` reports dependency
  failures.
- Confirm health responses and logs contain no secrets.

### Exit criteria

The hosting platform can distinguish a running process from an application that
is ready to receive traffic.

## Stage 5 Define Render infrastructure as code

Add a root `render.yaml` Blueprint so the hosted resources are reproducible.

### Web service

Configure:

- Docker runtime using the root Dockerfile and repository root as build context.
- Singapore region.
- One instance for the initial demo.
- Health-check path `/ready` after readiness behavior is verified.
- Pre-deploy migration command.
- Automatic deployment only after repository checks pass.

### PostgreSQL

Configure:

- The same Singapore region as the web service.
- A dedicated application database and user.
- Private/internal connectivity only where supported.
- `DATABASE_URL` injected from the database resource rather than copied into
  source or configuration files.

### Secrets

Mark the Groq key and demo credentials for dashboard entry. Generate the
retrieval-token secret through the platform where possible. Do not place secret
values in `render.yaml`.

### Continuous integration gate

Run the existing repository verification plus the final image build before an
automatic deployment:

```bash
make verify
docker build --platform linux/amd64 -t pulse-demo .
```

### Exit criteria

A team member can recreate the service and database from the repository plus
privately supplied secrets without reconstructing the topology manually.

## Stage 6 Deploy and perform hosted acceptance testing

### Deployment sequence

1. Merge the completed container, database, authentication, and health-check
   stages.
2. Create the Render resources from the Blueprint.
3. Enter the required secret values.
4. Provision PostgreSQL.
5. Build the application image.
6. Run migrations.
7. Run `seed-demo.sh` once.
8. Start the web service.
9. Enable the verified HTTP health check.
10. Record the deployed commit SHA and deployment time.

### Acceptance tests

Run these tests against the public URL from a private browser window and from a
device outside the developer machine:

- Anonymous access is rejected.
- The shared credentials open the application.
- Financial Adviser and Marketing role selection work.
- Contacts and campaigns load from PostgreSQL.
- Chat sessions persist after browser refresh and container restart.
- Campaign discovery and explainable matching work.
- Campaign clarification, draft generation, revision, and structured review
  work.
- Stale draft revisions are rejected and reloaded correctly.
- Email behavior is clearly labelled and remains simulated.
- No live company endpoint or real client data is used.
- Application logs contain no credentials, provider keys, database URLs, or
  client-sensitive content.

### Exit criteria

The hosted environment passes the documented smoke test from outside the local
development network.

## Stage 7 Prepare the tester and operator handoff

Create or update:

```text
backend/docs/deployment.md
backend/docs/demo_test_guide.md
```

`deployment.md` should cover:

- Implemented architecture and ports.
- Hosting resources and ownership.
- Required environment-variable names.
- Migration and synthetic seeding procedures.
- Deployment, rollback, and restart procedures.
- Health checks and log locations.
- Credential rotation.
- Demo reset and environment shutdown.

`demo_test_guide.md` should cover:

- The application URL.
- How to enter the shared credentials.
- Which prototype role to choose.
- Two or three concise test scenarios.
- The synthetic-data and simulated-email limitations.
- Known functional gaps.
- How and where to provide feedback.

Provide the actual password separately from the repository and documentation:

```text
URL:      https://example.invalid
Username: pulse-tester
Password: supplied through a private channel
Expires:  agreed test-environment expiry date
```

Use a randomly generated password of at least 20 characters. Rotate it after
the testing window and remove the hosted environment when it is no longer
needed.

### Exit criteria

A tester can access and evaluate the application without developer assistance,
and another team member can deploy, reset, rotate, or shut down the environment.

## Optional Stage 8 Implement individual user authentication

Complete this only if the environment will remain online, hold non-synthetic
data, or require individual accounts. Treat it as a separate product and data
ownership change rather than part of the quick demo deployment.

The work should include:

- Password-hashed user accounts.
- Login and logout endpoints.
- Secure `HttpOnly` and `SameSite` session cookies.
- Session expiry and revocation.
- CSRF protection for mutations.
- Server-derived tenant, adviser ID, and role.
- Removal of trust in browser-supplied `fa_id` and role values.
- Per-user audit records and deliberate account lifecycle management.

## Proposed pull request sequence

1. `deploy/containerise-full-stack`
2. `deploy/database-migration-and-compose`
3. `deploy/demo-authentication`
4. `deploy/health-and-config-hardening`
5. `deploy/render-blueprint`
6. `docs/deployment-and-test-handoff`

Each pull request should include focused tests and leave the normal local
development workflow usable. When the deployed topology, public port, storage
ownership, or integration boundaries change, update `Architecture.svg`, its
rendered image, the root README, and the API contract as required by the
repository documentation guide.

## Completion criteria

The deployment work is complete when:

- One reproducible Docker image serves the frontend and backend through one
  public origin.
- FastMCP is internal and reachable by FastAPI.
- Managed PostgreSQL is prepared through repeatable migrations and deliberate
  synthetic seeding.
- The complete public application is protected by shared demo credentials.
- Secrets exist only in the hosting provider's secret configuration.
- Health checks distinguish process liveness from dependency readiness.
- The full repository verification and hosted smoke tests pass.
- Testers receive a URL, private credentials, scenarios, limitations, and an
  expiry date.
- No real client data, live company connection, autonomous financial advice, or
  production security claim is introduced.

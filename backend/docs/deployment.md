# Hosting PULSE on Render Free

The repository supports a free, temporary shared demo. The image serves React
from FastAPI and starts FastMCP on loopback. PostgreSQL uses Render's internal
connection string. Hosted configuration requires shared authentication, stable
signing secrets and mock email. The normal local Make workflow is preserved.

## Costs and expiry

Choose Free for both resources, use the included HTTPS `onrender.com` URL and a
Groq Free key. Do not enable paid resources or Groq Developer billing. A free
Render workspace without a payment method avoids automatic overage charges;
exhausted quotas can suspend service/builds instead. Check account billing
settings before rollout. Code cannot determine a provider key's billing plan.

Render Free web services sleep after 15 idle minutes and take approximately a
minute to wake. The workspace gets 750 free instance hours monthly. Free
PostgreSQL has 1 GB storage, no backups and expires after 30 days. It is then
inaccessible and is deleted after a further 14-day upgrade grace period. Keep
the test window under 30 days. Do not use scheduled pings to evade idle sleep.
Build minutes and bandwidth also have quotas. Private outbound connections to
same-region databases are supported on Free.

Sources checked 2 November 2026: [Render free limits](https://render.com/docs/free),
[deployment lifecycle](https://render.com/docs/deploys),
[Blueprint reference](https://render.com/docs/blueprint-spec),
[Groq Free limits](https://console.groq.com/docs/rate-limits).

## Runtime and database ownership

```text
Browser -> Render HTTPS -> FastAPI 0.0.0.0:$PORT
                           |-- Basic Auth and same-origin mutation checks
                           |-- React assets and direct + /api routes
                           `-- FastMCP 127.0.0.1:8001/mcp
Both backend processes -> managed PostgreSQL via private connection
API orchestration -> Groq Free over HTTPS
```

The root Dockerfile builds React with Node 22, installs locked Python 3.11
dependencies and runs as a non-root user. Company references and local secrets
are excluded from the image. Vite does not run in hosting. FastAPI listens on
Render's `$PORT`; local Make startup still defaults to 4000. The container trusts
its reverse proxy's forwarded scheme for origin checks; do not expose it to
untrusted traffic outside that proxy arrangement.

Free services lack pre-deploy commands, shell access and one-off jobs.
`deploy/start.sh` runs `deploy/database.py bootstrap` before listening.
The runner applies an explicit SQL manifest under a transaction-scoped advisory
lock. Schema, enabled seeds and checksummed `pulse_deploy_migration` entries
commit together. Failure rolls everything back and stops startup without logging
connection details. Existing seed BEGIN/COMMIT wrappers are removed so the runner
owns the transaction. Overlapping starts serialize with bounded lock waits.

`DEMO_SEED_ON_START=true` enables only checked-in synthetic records. Each seed
file runs once per database. Restarts preserve edits and deleted rows. You can
set it false after the first successful deployment. Schema-only `migrate` and
explicit `seed` commands are also supported locally. Applied files are immutable:
append a new migration file to the manifest for changes. This is a small demo
runner, not a general production migration framework. Keep migrations compatible
with the prior app version while Render rolls out a new image.

Do not run backend/setup.sh on Render or point bootstrap at company/unrelated
databases. No reset endpoint or destructive reset command is provided. The
official campaign and campaign_member schemas are unchanged.

## Settings

| Variable | Value or source |
| --- | --- |
| DATABASE_URL | Render-injected internal PostgreSQL connection string |
| PULSE_HOSTED_DEMO | true |
| FRONTEND_DIST | /app/frontend-dist, set in image |
| DEMO_AUTH_ENABLED | true |
| DEMO_AUTH_USERNAME | Privately supplied shared username |
| DEMO_AUTH_PASSWORD | Random shared password of at least 20 characters |
| GROQ_API_KEY | Key from a Groq Free account |
| LLM_BASE_URL, LLM_MODEL | Existing Groq defaults; check Free model availability |
| MCP_SERVER_URL | http://127.0.0.1:8001/mcp |
| EMAIL_DELIVERY_MODE | mock; hosted live mode is rejected |
| PULSE_CAMPAIGN_RETRIEVAL_SECRET | Stable generated secret, at least 32 characters |
| PULSE_CAMPAIGN_PREVIEW_SECRET | Separate stable generated secret, at least 32 characters |
| DEMO_SEED_ON_START | true for initial once-only synthetic seeding |

Missing required settings stop startup. Never put secrets in Git, build args,
screenshots or Vite variables. No GWM credentials are needed. Rotate shared
credentials after testing. Rotating signing secrets invalidates outstanding tokens.

## Local rehearsal

Set `DEMO_AUTH_PASSWORD`, `PULSE_CAMPAIGN_PREVIEW_SECRET`, and
`PULSE_CAMPAIGN_RETRIEVAL_SECRET` in your shell. Generate random values with a
password manager or `openssl rand -hex 32`; do not commit them. Set a Groq Free
key only for live chat tests. Compose's synthetic fallback key deliberately
cannot call the model provider.

From the repository root:

```bash
docker compose up --build
```

Open http://localhost:4000 using username `tester` and your supplied password.
Stop other processes on port 4000 first. Compose stores PostgreSQL 16 data in a
named volume and exposes no database port. Its passwordless database access is
only for this isolated local rehearsal. `docker compose down` preserves data;
adding `-v` destroys it and is not part of normal shutdown.

For schema-only local execution:

```bash
docker compose run --rm app python /app/deploy/database.py migrate
```

## Render rollout

1. Push the reviewed implementation to the private team repository.
2. Create a Blueprint using render.yaml in a free Render workspace. Check both
   resources say Free, region Singapore, no disks or paid additions. Only one
   free database is allowed per workspace; do not delete an existing unrelated
   database if that limit is already reached.
3. Enter demo username/password and a Groq Free key privately. Render generates
   both signing secrets and supplies the internal database URL. The Blueprint
   disables external database access with `ipAllowList: []`.
4. Let the first build migrate, seed and start. `/ready` checks PostgreSQL and an
   MCP tool discovery with a four-second total timeout. It never calls Groq.
5. Complete acceptance below, then share the URL and credentials privately.
   Record the deployed commit, environment owner, test window and DB expiry.
6. Release later changes manually after verification. No paid CI service is
   required. Do not bypass SQL checksum failures by deleting the ledger.

## Acceptance

Run the repository AGENTS.md verification commands plus `npm test` in frontend.
`make verify` does not include the Node tests. Deployment PostgreSQL tests use
disposable databases when `PULSE_DEPLOY_TEST_DATABASE_URL` points to a local test
server with CREATEDB permission. Never supply a hosted or company URL.

- Anonymous/incorrect credentials cannot access assets, API docs or either API
  route form. Only `/live` and `/ready` are publicly readable generic checks.
- Valid credentials load React and SPA refreshes. Unknown API paths/missing
  assets return 404. Same-origin mutations succeed; cross-origin writes fail.
- DB/MCP outages produce generic readiness 503 responses, with no model call.
- Repeated bootstrap preserves edits; failing SQL rolls back. Chats and drafts
  persist through application restart.
- Discovery, matching, clarification, revision, signed preview and explicit
  draft campaign creation work. Stale revisions fail; retries do not duplicate.
- Check seed campaign schedules against the test window: discovery uses today's
  Singapore date; matching retains the fixed demo date.
- Validate cold starts and Groq rate-limit behavior with the invited testers.

## Limitations and handoff

Local verification on 2 November 2026: Docker build, non-root/asset checks,
PostgreSQL 16 bootstrap/rollback/checksum/concurrency tests, authenticated HTTP
smoke checks and chat persistence after container restart passed. The smoke
container stayed below its 512 MB limit (about 191 MB idle after restart).
No Groq request or real email was sent. Frontend tests, type checking/build,
Python/shell checks and Terraform format/validation passed.

The separately enabled existing `test_campaign_current_postgres.py` suite has
five failures reproducible on an empty test database: three outdated seed-count
expectations and two dictionary-style accesses on tuple rows. Those existing
tests were not rewritten in this deployment change. Hosted acceptance, actual
Groq Free model behavior and real Render resource provisioning remain unverified.

The hosted smoke test also exercises fresh seed compatibility. The REST and
frontend campaign contracts accept the seed's `inactive` status without
activating those campaigns or changing the official schema.

The conversational email adapter still expects legacy tables omitted from fresh
setup. It needs a separate consent-safe schema migration before it can be
advertised as working. Mock mode prevents live delivery but does not repair
that workflow. The campaign-detail email UI is a separate simulation and also
needs current-schema acceptance. Do not create legacy mock tables to mask this.

Tasks/pipeline remain browser-local. Shared credentials do not isolate testers:
those selecting the same adviser share synthetic records. Basic credentials can
remain browser-cached; closing the private window ends that browser session.
CRM sign-out only clears role selection. This is not production authentication.

Provide testers with scenarios, expiry date and these limits. An application
rollback does not revert SQL or recover data. Before the database expires,
decide whether an operator-managed export of synthetic state is needed; Free
has no backups. Do not upgrade under this zero-cost scope. Remove only the
identified demo resources at the end after confirming retention needs, and
revoke the demo provider key. Hosted acceptance remains pending until performed
against an actual Render URL.

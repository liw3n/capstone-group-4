# Hosting PULSE on Render Free with Supabase Free PostgreSQL

The repository supports a free, temporary shared demo. The image serves React
from FastAPI and starts FastMCP on loopback. PostgreSQL uses Supabase's shared
session pooler over the public internet with TLS, not Render's private network.
Hosted configuration requires shared authentication, stable
signing secrets and mock email. The normal local Make workflow is preserved.

## Deployment record — 5 November 2026

- Tester URL: https://pulse-demo-nail.onrender.com
- Deployed source: `main`, commit `2ab0408015966126e791b8eb84afc72d0a3bfddd`.
- Render: `pulse-demo`, Blueprint-managed Docker web service on Free.
- Supabase: dedicated `pulse-demo` project in Singapore, Free organization.
  Data API was disabled in the project creation form.
- At approximately 22:42 Singapore time, Render reported **Deploy succeeded | Live**.
  Logs showed all eight schema files and four synthetic seed files applied,
  FastMCP started on loopback, and repeated `/ready` responses of HTTP 200.
  An unauthenticated request to `/` returned HTTP 401, as intended.
- The initial deployment failed with the generic bootstrap error. After the
  operator increased `DEMO_AUTH_PASSWORD` to at least 20 characters and redeployed,
  bootstrap and startup succeeded. Check this validation requirement when
  troubleshooting; the generic message can also cover other configuration/SQL errors.

This verifies provisioning and startup, not full hosted acceptance. The tester
reported difficulty signing in; successful authenticated login has not yet been
confirmed. Next, verify the shared login, contacts/campaigns, live Groq chat and
the campaign review/confirmation flow. Restart persistence, pause recovery,
TLS inspection and an independent Data API exposure check also remain pending.
Do not mark the full acceptance checklist complete based on `/ready` alone.

Tester credentials are the values of `DEMO_AUTH_USERNAME` and
`DEMO_AUTH_PASSWORD` in Render, shared privately by the operator. No credential,
database connection string or provider key is recorded here. A separate deployment
attempt in the repository owner's workspace was reported; its current state is
unverified. Do not delete or modify it without confirming ownership and retention.

## Costs and inactivity

Choose a Render Free web service and a Supabase Free project, use the included
HTTPS `onrender.com` URL and a
Groq Free key. Do not enable paid resources or Groq Developer billing. A free
Render workspace without a payment method avoids automatic overage charges;
exhausted quotas can suspend service/builds instead. Check account billing
settings before rollout. Code cannot determine a provider key's billing plan.

Render Free web services sleep after 15 idle minutes and take approximately a
minute to wake. The workspace gets 750 free instance hours monthly. Free
Supabase PostgreSQL has 500 MB database storage and no fixed 30-day expiry.
Supabase can pause Free projects after seven days of low activity; check the
dashboard and restore a paused project before testing. A paused DB makes PULSE
unready, and bootstrap cannot complete until it is restored. Do not rely on
health probes to prevent pausing or use scheduled pings to evade free-tier sleep.
Plan operator-managed exports for data worth retaining, not paid backup add-ons.
Build minutes, bandwidth and database connections also have quotas. No paid
IPv4 add-on, Pro organization, PITR, custom domain or private networking is needed.

Sources checked 5 November 2026: [Render free limits](https://render.com/docs/free),
[deployment lifecycle](https://render.com/docs/deploys),
[Blueprint reference](https://render.com/docs/blueprint-spec),
[Groq Free limits](https://console.groq.com/docs/rate-limits),
[Supabase Free limits](https://supabase.com/kb/faqs/platform/database-only-cost),
[project pausing](https://supabase.com/docs/guides/platform/free-project-pausing),
[PostgreSQL connections and SSL](https://supabase.com/docs/guides/database/connecting-to-postgres),
[disabling the Data API](https://supabase.com/docs/guides/api/securing-your-api#disable-the-data-api).

## Runtime and database ownership

```text
Browser -> Render HTTPS -> FastAPI 0.0.0.0:$PORT
                           |-- Basic Auth and same-origin mutation checks
                           |-- React assets and direct + /api routes
                           `-- FastMCP 127.0.0.1:8001/mcp
Both backend processes -> public TLS -> Supabase session pooler :5432 -> PostgreSQL
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
Timeouts are set with transaction-local SQL rather than connection startup
options, keeping bootstrap and readiness compatible with managed poolers.

`DEMO_SEED_ON_START=true` enables only checked-in synthetic records. Each seed
file runs once per database. Restarts preserve edits and deleted rows. You can
set it false after the first successful deployment. Schema-only `migrate` and
explicit `seed` commands are also supported locally. Applied files are immutable:
append a new migration file to the manifest for changes. This is a small demo
runner, not a general production migration framework. Keep migrations compatible
with the prior app version while Render rolls out a new image.

### Seed-history repair — 7 November 2026

The baseline `mock_contact.sql` and `mock_campaign_member.sql` are restored
byte-for-byte to deployed commit `2ab0408`. Editing those already-applied files
caused checksum rejection when deploying the recommendation feature. Never
delete or rewrite `pulse_deploy_migration` entries to bypass that protection.

Two new immutable files in `tables/mock_data/`, listed in `SEED_UPDATES` in
`deploy/database.py`, carry the changes:

- `20261107_add_demo_contacts.sql`: adds synthetic clients 37–100 without
  overwriting existing IDs; fills Demo Client J's missing birth date only when
  the guarded baseline fields and creation/update timestamps remain unchanged.
- `20261107_add_demo_members.sql`: adds the two intended memberships only if
  parents are present/not deleted and no prior membership (even soft-deleted)
  exists. No outreach is sent.

Fresh demos run baseline seeds followed by these updates. Existing databases
with all baseline seed ledger entries receive updates even with
`DEMO_SEED_ON_START=false`; unseeded databases do not receive synthetic data.
Each update is checksummed and runs once under the existing transaction/lock.
`Staged` log lines precede commit; only `Database bootstrap committed successfully`
confirms persistence. Failure rolls back the whole attempt, including new tables.
Errors now distinguish settings, unavailable DB operations, changed manifest files
and SQL execution failures without printing raw provider errors or credentials.

Local `setup.sh` includes the new idempotent SQL after baseline seeds, but remains
the separate reprovisioning workflow (not the hosted once-only ledger workflow).
For future data changes, append another `SEED_UPDATES` entry rather than editing
any applied file, and test both an empty database and an existing seeded database.
This repair has not yet been deployed to Render. Commit/push it and manually
deploy the reviewed commit, then check commit confirmation and `/ready`.
Do not reset Supabase. Databases initialized from a different edited baseline
require separate reconciliation; this repair targets the original deployed ledger.

Repair verification: 393 backend tests passed, 47 unrelated opt-in tests skipped;
14 deployment tests include PostgreSQL 16 fresh setup, original-ledger upgrades,
once-only updates, edit/deletion preservation, rollback and checksum/redaction
checks. All 32 frontend tests, type checking/build, Python compilation, shell
syntax and Terraform format/validation passed. Existing frontend bundle and
test WebSocket-port warnings remain. Only a disposable local DB was used.

Do not run backend/setup.sh on Render or point bootstrap at company/unrelated
databases. No reset endpoint or destructive reset command is provided. The
official campaign and campaign_member schemas are unchanged.

## Settings

| Variable | Value or source |
| --- | --- |
| DATABASE_URL | Privately supplied Supabase session-pooler PostgreSQL URI, port 5432, with sslmode=require |
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

## Supabase database setup (before starting Render)

1. Create a dedicated project in a **Free** Supabase organization, preferably
   Singapore near the Render service. Do not reuse a company or unrelated project.
   Save the database password privately. This is separate from the tester login.
2. In the dashboard's Data API integration settings, turn **Enable Data API off**
   before creating/seeding PULSE tables. This is mandatory: our SQL schemas do
   not implement Supabase Auth/RLS, and default public-schema grants can otherwise
   expose tables through auto-generated APIs outside PULSE's Basic gate. Do not
   enable Realtime publications or expose these tables through other services.
3. In **Connect**, select **Session pooler**, not Transaction pooler or Direct.
   Copy the PostgreSQL URI exactly as provided: the pooler hostname and username
   are project-specific, the port is **5432**, and the database is **postgres**.
   Keep the project suffix in the username. Insert the database password with
   reserved URI characters percent-encoded; do not use a Supabase API key.
4. Add `sslmode=require` (`?` for the first URI query option, otherwise `&`).
   This refuses plaintext fallback. Enable SSL enforcement in Supabase as well.
   `require` encrypts but does not verify server identity; `verify-full` additionally
   needs the appropriate trusted CA supplied to the container via `sslrootcert`.
   Do not claim certificate verification when using only `require`.
5. Store the complete URI only as Render's secret `DATABASE_URL`. Never place it
   in Git, frontend/Vite settings, screenshots or build arguments. No Supabase
   JavaScript SDK, anon key, service-role key or Supabase Auth integration is used.

The shared session pooler supports IPv4 without the paid IPv4 add-on and retains
session semantics for the existing psycopg callers. Do not substitute transaction
pooling (port 6543); it has different prepared-statement/session behavior.
The dedicated project's database owner is used for startup DDL and runtime SQL
in this bounded synthetic demo, not as a production least-privilege design.
The official table definitions and local PostgreSQL workflow are unchanged.

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
2. Complete Supabase setup above, then create a Blueprint using render.yaml in a
   free Render workspace. It creates **one web service only**, Free, Singapore,
   with no Render database, disks or paid additions.
3. Enter the Supabase `DATABASE_URL`, demo username/password and Groq Free key
   privately. Render generates both signing secrets. Confirm Supabase's Data API
   is disabled and its project is running before the first deployment.
4. Let the first build migrate, seed and start. `/ready` checks PostgreSQL and an
   MCP tool discovery with a four-second total timeout. It never calls Groq.
5. Complete acceptance below, then share the URL and credentials privately.
   Record the deployed commit, environment owner, test window and pause/export
   checks. Supabase resources are managed separately from the Render Blueprint.
6. Release later changes manually after verification. No paid CI service is
   required. Do not bypass SQL checksum failures by deleting the ledger.

If an earlier Render database was already provisioned, changing this Blueprint
does not migrate its data. Do not delete it or assume that changing `DATABASE_URL`
copies records. Obtain a separate approved export/restore plan if any state must
be retained. For a fresh synthetic demo, the new empty Supabase database receives
the checked-in seeds; existing chats and edits will not appear there automatically.

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
- Check seed campaign schedules against the test window: lookup and matching use
  today's Singapore date with inclusive bounds; discovery uses status-only
  eligibility and reports today's date as context.
- Validate cold starts and Groq rate-limit behavior with the invited testers.
- Confirm the running connection uses TLS (`pg_stat_ssl` for the current backend),
  the session-pooler URL is selected, and Supabase's Data API is disabled. Verify
  auto-generated REST endpoints cannot return PULSE tables, even with a project
  publishable/anon key. Never publish credentials while recording these checks.
- Check restore-from-pause and Render redeployment/recovery before a scheduled
  demo. Retest bootstrap and readiness on the actual Supabase PostgreSQL version;
  local PostgreSQL 16 tests are not proof of hosted pooler compatibility.

## Limitations and handoff

Supabase revision verification on 5 November 2026: backend tests passed (335
passed, 47 opt-in database tests skipped); frontend tests passed (24), as did
type checking/build, Python compilation, shell syntax, Terraform format/validation
and local Blueprint free-service/secret checks. Added unit regressions cover
transaction-local timeout setup in bootstrap and readiness. Frontend tooling
still reports existing bundle-size/import and test WebSocket-port warnings.
The updated architecture SVG was rendered to PNG and visually checked. Those
local checks did not provision cloud resources or call the model provider;
subsequent hosted startup results are recorded above.

Local verification on 2 November 2026: Docker build, non-root/asset checks,
PostgreSQL 16 bootstrap/rollback/checksum/concurrency tests, authenticated HTTP
smoke checks and chat persistence after container restart passed. The smoke
container stayed below its 512 MB limit (about 191 MB idle after restart).
No Groq request or real email was sent. Frontend tests, type checking/build,
Python/shell checks and Terraform format/validation passed.

The separately enabled existing `test_campaign_current_postgres.py` suite has
five failures reproducible on an empty test database: three outdated seed-count
expectations and two dictionary-style accesses on tuple rows. Those existing
tests were not rewritten in this deployment change. Full hosted acceptance and
actual Groq Free model behavior remain unverified. Render/Supabase provisioning
and bootstrap have now succeeded as recorded above; the earlier Docker smoke
results used local PostgreSQL, not Supabase.

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

Provide testers with scenarios, test window and these limits. An application
rollback does not revert SQL or recover data. Assign an owner to check project
pausing, quota usage and operator-managed exports of synthetic state. Do not
upgrade under this zero-cost scope. Remove only the
identified demo resources at the end after confirming retention needs, and
revoke the demo provider key. Complete the remaining hosted acceptance checks
against the deployed URL and record their results separately from startup checks.

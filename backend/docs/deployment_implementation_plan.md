# PULSE free Render + Supabase deployment implementation plan

Status: repository implementation; hosted acceptance pending. This replaces the
earlier paid-compute design and the expiring Render Free database plan.
Revised 5 November 2026. All services must remain free.
Operational instructions are in [deployment.md](deployment.md).

## Agreed scope

- One Render Free Docker web service in Singapore and a separate Supabase Free
  PostgreSQL project, preferably Singapore, connected via the public TLS session
  pooler on port 5432. This is not Render-private networking.
- React production files served by FastAPI on the public `$PORT`; FastMCP on
  `127.0.0.1:8001` inside the container. One HTTPS URL and shared Basic login.
- Groq Free for inference, synthetic data only, email restricted to mock mode.
- No paid workspace upgrade, paid compute, disk, domain, one-off job,
  pre-deploy command, IPv4 add-on or preview stack. Quotas, Render idle sleep and
  Supabase low-activity pausing are accepted limitations; no fixed 30-day DB expiry.

## Implementation sequence and acceptance

| Stage | Repository implementation | Acceptance |
| --- | --- | --- |
| Container | Root Dockerfile and .dockerignore; Node 22 frontend build, Python 3.11 backend, non-root runtime | React and both processes start; API paths retain JSON errors |
| Database | deploy/database.py and deploy/start.sh; explicit SQL order, advisory lock, transactional checksum ledger | Repeat startup preserves edits; failures roll back; seeds run only once |
| Access | Shared Basic middleware and same-origin mutation checks | Assets/API protected, cross-origin writes rejected, missing settings stop hosted startup |
| Health | Generic /live and bounded DB query + MCP tool discovery /ready | Dependency failure returns 503 without secrets or a model call |
| Render | render.yaml creates one Free web service; secret DATABASE_URL supplied manually; manual releases | Dashboard confirms Free service and Supabase session-pooler URL with TLS |
| Supabase | Operator creates a separate Free project and disables Data API before bootstrap | Free plan, correct region, TLS session connection and no public table API access verified |
| Rehearsal | compose.yaml and deployment tests | Local image and fresh PostgreSQL smoke test |
| Hosted rollout | Operator follows deployment.md | External HTTPS acceptance, restart persistence, pause recovery, export plan and owner recorded |

Free-tier migration setup runs at startup because paid pre-deploy hooks and
shell access are unavailable. Seeding is an explicit Blueprint setting with
once-only database bookkeeping. An application rollback does not roll back SQL.
Changes to already applied SQL fail checksum validation and require a new
explicit migration file; do not delete the ledger to bypass the check.

Both retrieval and campaign-preview signing secrets are stable and generated
through Render. `/live` and `/ready` alone bypass shared authentication so Render
can probe readiness. Other routes, including documentation and `/health`, remain
protected. The shared gate is not adviser authentication or a tenant boundary.

## Work still outside hosting

Conversational email still depends on legacy tables absent from fresh setup.
It needs a separate consent-safe adapter migration before being advertised as
working; mock mode alone does not fix persistence. No live email is permitted.
Task/pipeline persistence, full outcome tracking and individual accounts remain
separate product work. Official campaign schemas remain unchanged.

No cloud resources have been created by this repository update. Render and
Supabase Free accounts, a private repository connection, a Supabase session-pooler
URI, demo credentials and a Groq Free key are required for rollout. Do not publish
credentials in Git. Supabase is used only as PostgreSQL; no client SDK or Auth
migration is needed. Local Compose keeps its isolated PostgreSQL 16 service.
An existing database is not copied by changing the URL; retained state requires
a separately approved export/restore before any old resource is removed.

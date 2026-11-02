# PULSE free Render deployment implementation plan

Status: repository implementation; hosted acceptance pending. This replaces the
earlier proposed paid-compute/pre-deploy design. All services must remain free.
Operational instructions are in [deployment.md](deployment.md).

## Agreed scope

- One Render Free Docker web service and one Render Free PostgreSQL database,
  both in Singapore, connected over the private network.
- React production files served by FastAPI on the public `$PORT`; FastMCP on
  `127.0.0.1:8001` inside the container. One HTTPS URL and shared Basic login.
- Groq Free for inference, synthetic data only, email restricted to mock mode.
- No paid workspace upgrade, paid compute, disk, domain, one-off job,
  pre-deploy command or preview stack. Quotas/expiry are accepted limitations.

## Implementation sequence and acceptance

| Stage | Repository implementation | Acceptance |
| --- | --- | --- |
| Container | Root Dockerfile and .dockerignore; Node 22 frontend build, Python 3.11 backend, non-root runtime | React and both processes start; API paths retain JSON errors |
| Database | deploy/database.py and deploy/start.sh; explicit SQL order, advisory lock, transactional checksum ledger | Repeat startup preserves edits; failures roll back; seeds run only once |
| Access | Shared Basic middleware and same-origin mutation checks | Assets/API protected, cross-origin writes rejected, missing settings stop hosted startup |
| Health | Generic /live and bounded DB query + MCP tool discovery /ready | Dependency failure returns 503 without secrets or a model call |
| Render | render.yaml uses two Free resources; no external DB access; manual releases | Dashboard confirms Free plans and internal URL before deployment |
| Rehearsal | compose.yaml and deployment tests | Local image and fresh PostgreSQL smoke test |
| Hosted rollout | Operator follows deployment.md | External HTTPS acceptance, restart persistence, expiry and owner recorded |

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

No cloud resources are created by these repository files. A Render account,
private repository connection, demo credentials and Groq Free key are required
for the operator to complete rollout. Do not publish credentials in Git.

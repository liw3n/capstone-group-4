# Backend Agent Guide

## Scope

Applies to everything under `backend/`. Read the more specific guide in
`app/`, `mcp/`, `docs/`, `tables/`, or `terraform/` before editing there.

The backend is a Python 3.11+ project managed by `uv`. `pyproject.toml` and
`uv.lock` are the dependency source of truth. Keep the lockfile synchronized
when dependencies change; do not hand-edit it.

The backend exists to support an adviser-facing campaign companion, not a
general-purpose chatbot. Product, confidentiality, and human-confirmation rules
in the repository root apply to all API, LLM, MCP, storage, and infrastructure
changes.

## Setup and common commands

Run these from `backend/` unless stated otherwise:

```bash
uv sync --frozen
uv run python -m compileall -q app mcp
uv run pytest
uv run uvicorn app.main:app --reload --port 4000
```

`./setup.sh` is an integration/provisioning operation: it starts FakeCloud,
applies Terraform, writes `.env`, and creates tables. Set
`DEPLOY_FAKECLOUD_ECS=1` to additionally build/push the image and reapply
Terraform. Do not use it as a lightweight unit-test command.

## Change rules

- Keep request/response validation in Pydantic models and storage concerns out
  of route handlers.
- Convert database failures into intentional API behavior; do not expose raw
  connection details or stack traces.
- Use parameterized SQL. Never interpolate user input into SQL strings.
- Treat `DATABASE_URL` as a secret even though local setup uses test values.
- Keep LLM access server-side. Never expose `GROQ_API_KEY` or other provider
  credentials to the frontend.
- Tools that read CRM data must enforce adviser/tenant ownership and return the
  minimum data required. Prefer stable IDs, aggregates, and eligibility reasons
  over raw PDPA fields.
- Separate read-only tools from consequential tools. Outreach or CRM mutations
  require a preview and explicit adviser confirmation enforced by the server.
- Keep placeholder and synthetic tools unmistakably labelled in code and
  responses; never let the model describe them as production results.
- Keep Docker paths, Uvicorn import paths, exposed port `4000`, setup commands,
  and Terraform container settings aligned.
- New behavior requires tests. Prefer FastAPI `TestClient` for routes and
  isolate persistence behind fixtures/fakes so unit tests do not require
  FakeCloud.

## Known gaps (current state)

- Campaign discovery, matching, performance, reference retrieval, draft
  preparation and selective draft revision use scoped synthetic data. Ordinary
  PULSE chat now persists validated drafts, routes active-draft turns explicitly,
  and can revise named fields or select revision-bound narrative alternatives
  across turns. Broad declarative field/value instructions enter this scoped
  route, while ordinary MCP tool intents retain precedence. Criteria revisions
  refresh dependent targeting metadata and client-facing copy; the MCP revision
  boundary itself remains read-only. Consent-safe
  outreach, interaction/task mutation and outcome tools remain incomplete.
- Campaign clarification state is persisted per tenant, adviser and chat
  session. Generated structured drafts and their current optimistic revision are
  retained separately from campaign records; short-lived option sets are stored
  separately from both draft content and chat prose.
- Adviser/session-scoped draft review routes support exact manual edits and
  selected-field regeneration through the same policy boundary. They update
  review state only; server preview tokens, confirmation and campaign creation
  remain unimplemented.
- Adviser identity is caller-supplied. There is no authentication or verified
  tenant middleware; current scope checks are prototype boundaries.
- There is no production CRM adapter for `gwm_api/`.
- There is no migrations framework, connection pool, structured logging,
  tracing, or production readiness probe.
- CORS allows every origin; acceptable for a local prototype, not production.
- Production and development dependencies are not separated.
- The optional ECS deployment applies infrastructure before the image
  build/push and may require Docker insecure-registry configuration; keep its
  local-only scope explicit.

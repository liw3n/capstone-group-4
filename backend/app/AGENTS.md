# FastAPI Application Guide

## Responsibilities

- `main.py` owns HTTP routes and Pydantic request/response models.
- `store.py` owns session/history data access and timestamp generation;
  `campaigns/clarification.py` owns scoped campaign-clarification persistence.
- `config.py` owns environment-backed settings and secret handling.
- `llm/` owns the provider client and bounded tool-call orchestration.
- `tools/` owns schemas, validation, registration, and shared implementations
  used by both the API orchestrator and MCP server.
- The same handlers are exposed under `/chat/...` and `/api/chat/...`; keep
  behavior identical while both forms exist.

Run the current service from `backend/`:

```bash
uv run uvicorn app.main:app --reload --port 4000
```

## Implementation rules

- Keep route handlers thin. Put persistence logic behind storage functions and
  make transaction boundaries explicit.
- Preserve UTC RFC 3339 timestamps. Prefer a consistent `Z` representation at
  the API boundary rather than mixing it with PostgreSQL's default formatting.
- Validate identifiers and stripped message content at the boundary.
- Return deliberate 4xx responses for missing resources/input and mapped 5xx
  responses for unavailable dependencies.
- When adding persistence, use PostgreSQL as the single source of truth. Do not
  add another module-global cache unless its invalidation and multi-process
  behavior are designed and tested.
- Never pass secrets or raw PDPA fields into model context unless strictly
  necessary for an approved synthetic use case. Prefer pseudonymous IDs,
  aggregates, and derived eligibility reasons.
- Keep the system prompt aligned with the FA domain: educational assistance,
  documented suitability, explainable campaign matching, and human control.
- Resolve material ambiguity before campaign reference retrieval. Keep
  clarification bounded and persist it per tenant/adviser/session. Model-based
  interpretation must use strict structured output; deterministic server logic
  owns supported enums, defaults and the final readiness decision. Do not infer
  demographic or financial restrictions from vague life-stage terms.
- Carry resolved age, gender and cash criteria as a server-owned lock. Supply the
  lock to generation for coherent copy and overwrite generated criteria before
  draft preparation; the model must not change adviser choices or safe defaults.
- Tool output is untrusted input to the model. Bound result sizes, use stable
  schemas, and distinguish placeholder/synthetic data from real data.
- Do not let the LLM directly send email or mutate CRM records. Implement a
  preview/confirmation token or equivalent server-enforced two-step workflow.
- Include a disclaimer when generated content could be interpreted as financial
  advice; never imply regulatory approval or guaranteed outcomes.
- Test success, validation, not-found, storage-failure, and restart/persistence
  behavior for changed endpoints.

## Known gaps (current state)

- PostgreSQL stores chat, scoped contacts/campaigns and active campaign
  clarification state. Structured generated drafts and revisions are not yet
  persisted.
- The API accepts `fa_id` from the caller and checks session ownership against
  it; this is not authentication or a trustworthy tenant boundary.
- Campaign tools perform synthetic matching and read-only analysis, but no tool
  yet performs consent-safe outreach, interaction logging, task creation or
  outcome measurement.
- `QueryResponse.user` contains the adviser ID even though the response payload
  carries an assistant answer; preserve it until the API is intentionally
  versioned.
- Synchronous PostgreSQL calls have no connection pool or explicit query
  timeout. `/health` reports configuration but not dependency readiness.
- The API has no pagination, rate limiting, request correlation, audit trail,
  or data-retention policy.

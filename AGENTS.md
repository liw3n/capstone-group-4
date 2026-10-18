# Coding Agent Guide

## Scope and precedence

This file applies to the whole repository. Read the nearest nested `AGENTS.md`
before changing files in a subdirectory; nested guidance adds to or overrides
this file.

Do not edit generated state (`__pycache__`, `.venv`, `.terraform`, Terraform
state, logs, PID files, or `.env`). Never commit credentials or a generated
database URL.

## Project objective and product north star

PULSE is a BT4103 capstone prototype exploring how AI and MCP can improve a
financial adviser's CRM workflow. Success is a limited but working, demo-ready
vertical slice plus a well-reasoned proposal; this is not a mandate to build a
full CRM or production financial-advice system.

The primary product direction is a human-supervised campaign companion:

1. discover and explain active campaigns;
2. segment synthetic clients using transparent criteria;
3. explain why each client was selected;
4. draft educational, compliant outreach;
5. require adviser confirmation and respect communication consent;
6. simulate or execute the authorised action, then log interactions;
7. create follow-up tasks and measure outcomes.

Preserve the full campaign loop when prioritising work. A generic chatbot or a
standalone infrastructure demo does not satisfy the project objective.

## Authoritative company resources

Read the relevant file under `docs/` before changing product behavior or the
data model:

- `Pulse Capstone.pdf`: scope, milestones, deliverables, and confidentiality.
- `FA Domain.docx`: Singapore FA workflows, campaign lifecycle, suitability,
  and the adviser's financial-literacy role.
- `Table Structure_GCRMDB.docx`: supplied GCRM table catalogue and PDPA fields.

These resources are company-provided and may contain confidential architecture
or infrastructure identifiers. Do not quote, publish, upload, or reproduce them
outside the project. Do not copy production hosts, credentials, client data, or
personal data into code, fixtures, logs, issues, prompts, or presentations.
Use synthetic data only.

## Repository map

- `backend/`: Python 3.11+ FastAPI service, a FastMCP prototype, local
  FakeCloud/AWS infrastructure, and PostgreSQL DDL.
- `frontend/`: project-owned React 19 + TypeScript CRM and PULSE chat frontend.
- `docs/`: handling guidance plus locally supplied, git-ignored company brief,
  FA-domain briefing, and GCRM schema reference.
- `gwm_api/`: handling guidance plus locally supplied, git-ignored OpenAPI
  documents for future server-side integration; they are not runnable services.

## Working conventions

- Keep changes narrowly scoped and preserve both route forms (`/chat/...` and
  `/api/chat/...`) unless an API migration is intentional.
- Run commands from the directory documented by the nearest `AGENTS.md`.
- Add or update tests for behavior changes. If the affected area has no test
  harness yet, call that out rather than claiming full verification.
- Keep AI recommendations explainable and grounded in tool output. Never present
  placeholder or synthetic results as production data.
- Require an explicit human confirmation immediately before consequential
  actions such as sending communications or mutating CRM records.
- Any generated financial advice must include an appropriate disclaimer. Prefer
  educational assistance and workflow support over autonomous advice.
- Enforce adviser/tenant ownership at every storage and tool boundary. Apply
  email/SMS opt-in rules before including a client in outreach.
- Update documentation and the architecture diagram when interfaces,
  deployment topology, ports, or data ownership change.
- Inspect `git status` before and after work. Do not overwrite unrelated local
  changes.

## Minimum verification

From the repository root:

```bash
cd backend && uv run pytest
cd ../frontend && npm run lint && npm run build
cd ..
python3 -m compileall -q backend/app backend/mcp
bash -n backend/setup.sh
terraform -chdir=backend/terraform fmt -check
```

Run `terraform validate` after `terraform init` is available. Backend-specific
checks and startup commands are in `backend/AGENTS.md`.

## Known gaps (current state)

- Campaign records and campaign UI state now use PostgreSQL through REST, and
  read-only MCP discovery/matching tools use those campaign rows. Consent-safe
  outreach, interaction/task mutation, and outcome tools remain incomplete.
- Contacts, campaigns and chat now use PostgreSQL through scoped APIs. Pipeline
  cards and tasks created during a session remain browser-local.
- Campaign generation now has a bounded, adviser/session-scoped hybrid
  clarification step before reference retrieval. Schema-constrained model
  extraction interprets natural language, while server validation owns supported
  targeting enums and safe defaults. Resolved age, gender and cash criteria are
  locked server-side before draft preparation, so generation cannot replace the
  adviser's choices. Validated structured drafts are stored separately from
  campaigns and returned by chat with a stable draft ID and optimistic revision.
  Cross-turn selective revision can regenerate one or several named fields while
  preserving unselected independent fields and rerunning policy validation.
  Criteria changes refresh dependent targeting summary/rationale and, for chat
  regeneration, dependent client-facing copy. Active-draft routing recognises
  declarative and compact field/value instructions while explicit discovery,
  matching, performance, follow-up and email intents retain precedence;
  explicit new-draft intent is required before replacing review context. Narrative alternatives
  are stored as short-lived, revision-bound option sets so numbered selections
  do not rely on parsing chat prose. The Campaigns workspace now provides a
  structured, prefilled review mode with optimistic manual edits, selected-field
  regeneration, stale-revision reload and a local read-only preview. Drafts remain review-only:
  server-issued preview tokens, confirmation and campaign creation are not yet
  implemented.
- `campaign`, `campaign_member`, `interaction`, and `task_item` are described by
  the company schema document, but their column definitions are absent. Do not
  invent a production-compatible schema without documenting the prototype
  assumptions.
- There is no real authentication/authorization or verified tenant boundary.
  UI role selection and request-supplied adviser IDs are prototype mechanisms.
- There is a small Node frontend test suite for campaign-draft review helpers
  and server-rendered UI. There is no browser end-to-end suite, CI workflow, or
  pre-commit configuration.
- FastMCP runs over HTTP on port `8001` in the API container, and the API calls
  it through the MCP protocol. Implemented campaign tools remain synthetic and
  read-only.
- Infrastructure remains a local FakeCloud prototype, not a production AWS
  design.

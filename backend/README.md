# PULSE Chat API

FastAPI backend for the PULSE chat popup. The service calls Groq through its
OpenAI-compatible API, discovers and invokes tools through FastMCP over HTTP,
and persists sessions and messages in PostgreSQL.

## Shared application setup

Follow the [team setup guide](../README.md#team-setup-and-development-workflow).
Run these from the repository root in macOS/Linux/WSL Bash, with all prerequisites
installed, including the standalone FakeCloud executable:

```bash
UV_PYTHON=3.11 make bootstrap
make doctor
```

Set your own `GROQ_API_KEY` in the ignored `backend/.env`, then:

```bash
make provision
make dev
```

`make provision` runs `setup.sh`, provisions the local database, writes its address
to `.env`, creates chat/mock tables and loads the synthetic seed SQL. The script
requires the standalone `fakecloud` executable, installed separately using the
[official installer](https://fakecloud.dev/docs/getting-started/install/):

```bash
curl -fsSL https://fakecloud.dev/install.sh | bash
command -v fakecloud
```

Install it before running `make provision`. The `localstack` Python dependency
does not provide this executable. `setup.sh` starts FakeCloud automatically;
keep Docker running so it can create the database container.

`make dev` starts FastAPI :4000, FastMCP :8001 `/mcp` and Vite :3000 together.
Present the feature through http://localhost:3000. `run_services.sh` is shared
startup infrastructure; discuss changes with the team before editing it. Do not
start a separate API Docker container alongside this workflow.

`DATABASE_URL` must be the generated address from provisioning. The old
`pulse-postgres:5432` value is for the previous direct Docker workflow. Keep the
example provider/model settings and `MCP_SERVER_URL=http://127.0.0.1:8001/mcp`
unless an intentional configuration change is agreed. Never commit `.env` or keys.

Shell scripts use LF line endings. The Dockerfile normalizes line endings for
optional image builds. The emulated ECS path is optional; set
`DEPLOY_FAKECLOUD_ECS=1` when running `make provision` to exercise it. It is not
required for `make dev` or the interim presentation.

## System architecture

[Architecture.svg](docs/Architecture.svg) shows the complete current system:
React CRM and PULSE chat, the Vite proxy, FastAPI, LLM orchestration, FastMCP,
Groq and PostgreSQL. It distinguishes browser-only non-campaign CRM state from
persisted campaign/chat data and labels the team Terraform/FakeCloud provisioning
workflow, optional ECS and planned company CRM integration. The SVG is the
editable source; the PNG is its synchronized rendered export.

## Endpoints

- `GET /health`
- `GET /contacts?fa_id=<id>`
- `POST /contacts?fa_id=<id>`
- `PUT /contacts/{contact_id}?fa_id=<id>`
- `GET /campaigns?role=<role>&fa_id=<id>`
- `POST /campaigns?role=<role>&fa_id=<id>`
- `PATCH /campaigns/{campaign_id}/state?role=<role>&fa_id=<id>`
- `GET /chat/sessions?fa_id=<id>`
- `POST /chat/new?fa_id=<id>`
- `GET /chat/history?session_id=<id>`
- `POST /chat/query`

See `docs/api_contract.md` for request and response details.

## Tools

The FastMCP server registers tools in `mcp/server.py`; the API retrieves their
schemas and calls them through `app/tools/mcp_registry.py`. Configure
`MCP_SERVER_URL` to the server's Streamable HTTP `/mcp` endpoint; it defaults to
`http://127.0.0.1:8001/mcp` when the API and MCP server run on the same host.

The registered tools include `recommend_clients_for_campaign`,
`get_active_campaigns`, `get_campaign_contact_performance`,
`get_campaign_contact_ranking`, `find_campaign_references`,
`prepare_campaign_draft`, `revise_campaign_draft`, `prepare_campaign_email`,
`confirm_campaign_email`, and `campaign_follow_up`. Campaign matching and scoped data access live in
`app/campaigns/`; shared follow-up handlers live in
`app/tools/campaign_follow_up.py`. Follow-up handlers query the mock engagement
table and currently return simulated client profile and portfolio data.

`find_campaign_references` searches a checked-in, approved synthetic pattern
catalogue before campaign drafting. It returns at most three explainable matches
and a five-minute signed token bound to the objective and request scope. It is
read-only and never queries client records or campaign tables. When
`PULSE_CAMPAIGN_RETRIEVAL_SECRET` is not set, the local prototype uses a random
process secret, so outstanding tokens intentionally become invalid when the MCP
process restarts.

`prepare_campaign_draft` verifies that token, permits only retrieved reference
citations and applies deterministic schema, disclaimer, targeting, unsupported-
claim and personal-data checks. It returns one review-required structured
artifact with `created: false`; it does not write a draft or campaign record.
Claim checks distinguish affirmative promises from explicit risk warnings such
as "returns are not guaranteed". Unsupported numeric rates and amounts remain
blocked, and claim failures identify only the safe field and rule name.
If generated client messaging or disclaimer text omits the required educational,
non-advice or individual-review language, the server appends a standard notice
and records a visible adviser-review warning instead of rejecting the draft.
After a successful preparation, the API renders every validated field with a
deterministic Markdown formatter and stops the model tool loop. This prevents a
later model summary from dropping fields and avoids an additional provider call.
For clear campaign-generation requests, the orchestrator invokes retrieval
server-side instead of asking the model to author a retrieval tool call. The
orchestrator first applies a bounded hybrid clarification gate. It normalizes
common punctuation locally, uses a strict structured model response to interpret
natural-language intent, and validates the result against server-owned targeting
enums. Underspecified planning focus and ambiguous or unsupported age/cash
language produce at most three questions before catalogue retrieval or draft
generation. Pending state is stored per tenant, adviser and chat session in
PostgreSQL, can be cancelled, and survives process restarts. Omitted gender and
cash restrictions remain unrestricted rather than being inferred. Only the
campaign objective and clarification answers are sent for intent extraction;
client records are not included.
Once the objective is ready, the model produces draft content and citations
through Groq's strict JSON Schema response mode with no tools. The API gives the
model the exact server-resolved age, gender and cash criteria so its summary and
rationale can agree, then overwrites the returned structured criteria with that
lock before preparation. It also retains and injects the exact objective and
signed retrieval token before calling preparation itself. This prevents model
changes to trusted values and removes provider-side tool-call generation from
the campaign workflow.

`revise_campaign_draft` is the Stage 6 read-only selective-revision boundary.
It accepts an authoritative validated draft, its objective and citations, an
explicit field list, and proposed values for exactly those fields. Server code
restores every unselected independent field, refreshes derived targeting summary
and rationale when criteria change, reruns complete schema and policy validation,
and returns the next review-only revision with `created: false`. It never reads
or writes campaign tables. The direct MCP boundary remains omitted from the
generic model tool list. Instead, Stage 7 stores the validated structured draft,
loads its authoritative tenant/adviser/session-scoped state for a revision
request, asks the model for only the explicitly selected values, and invokes the
boundary directly. Requests may revise one or several supported fields, and
successive turns advance the same draft from revision `n` to `n + 1`.

With an active draft, a state-aware turn resolver runs before new-campaign
generation. It distinguishes ordinary tool requests, selective revision,
narrative-option generation and selection, current-draft display, and explicit
new-draft intent. Requests such as `draft the full campaign` display the current
artifact; a new draft requires explicit replacement/new-campaign language.
Requests such as `give me five campaign name options` persist a 15-minute,
revision-bound option set without changing the draft. Selecting `the fifth
option` applies only that field through `revise_campaign_draft` and the same
optimistic update. Ordinary discovery, matching, follow-up, performance and
email tools remain on their existing routes.

Active-draft routing accepts declarative and compact field/value instructions
that omit `campaign` or `draft`. Explicit discovery, matching, performance,
follow-up and email intents retain precedence and bypass draft loading. For chat
criteria revisions, server-normalized age/gender/cash values override untrusted
model proposals and are supplied as authoritative context for dependent
description/message regeneration. The MCP boundary derives the demographic
summary and field-level rationale directly from the final criteria. Generated
targeting uses fixed bands, so strict requests such as `above 65` and `more than
250k` map to `65plus` and the two upper cash bands respectively, with a validation warning
that tells the adviser about the approximation.

Successful generation and revision responses include an optional
`campaignDraft` object alongside the existing `ai_answer`. It contains a stable
`draftId`, the current revision, the complete validated draft, provenance and
warnings. The draft row and the matching user/assistant exchange are committed
in one PostgreSQL transaction. Updates use optimistic locking, so a stale
revision cannot overwrite newer work. These writes affect only
`campaign_generation_drafts` and chat tables; they do not create or update
`mock_campaign`. Stage 8 exposes adviser/session-scoped GET, PATCH and selected-
field regeneration routes at `/campaign-drafts/{draft_id}` (and matching `/api`
forms). Manual edits and model proposals both pass through the same selective-
revision validation boundary and optimistic revision check.

The frontend opens the artifact in a prefilled review mode inside the existing
Campaigns workspace. It shows rationale, assumptions, warnings and synthetic
catalogue provenance, supports editing and multi-section regeneration, and has
a local read-only preview. It does not show a named audience or create a
campaign. Server-issued preview tokens and explicit campaign creation
confirmation remain later stages.
If an optimistic save is stale, the review reloads the latest scoped revision
in place rather than directing the adviser back through chat.

Alternative-generation responses additionally use optional
`campaignDraftOptions` structured state. The options are scoped to the tenant,
adviser, chat session, active draft and base revision; chat prose is never parsed
to recover a later numbered choice.

The MCP server serves `http://127.0.0.1:8001/mcp` using Streamable HTTP. Use
`make dev` or `make backend-dev` from the repository root to start the shared
backend processes; a standalone tool demo program is not required.

## Tests

```bash
uv run pytest
```

The automated tests mock the model provider and do not require an API key or make
network calls.


## Synthetic campaign recommendations

The contact catalogue (`/contacts/...` and `/api/contacts/...`) exposes the same
scoped `mock_client` rows used by MCP matching; there is no frontend contact
fixture. The REST campaign catalogue (`/campaigns/...` and `/api/campaigns/...`) persists
the campaign screens' definitions and mutable campaign state in the same
`mock_campaign` rows used by the MCP tools. The frontend no longer ships a
second campaign seed. The existing campaign-detail email modal remains a browser
simulation. PULSE email sends use the backend confirmation flow described below;
contacts, pipeline cards and tasks remain browser state.

PULSE can recommend synthetic clients for the selected seeded campaign using
`recommend_clients_for_campaign`. The model sees campaign ID and limit only;
the API supplies request-scoped adviser/tenant identity via MCP metadata.

The repository reads synthetic PostgreSQL tables created and seeded by
`make provision`. Verify both campaigns in the shared frontend after `make dev`.
The matching logic does not call Groq; automated unit/integration tests can verify
it independently, without a separate demo script.

See [prototype assumptions, SQL and frontend verification](docs/campaign_recommendations.md).

## Synthetic campaign contact history

`make provision` also creates `mock_campaign_contact_event` and loads fixed-date,
synthetic outreach records for the two seeded campaigns. Each event references
the existing campaign by `tenant_id` and `campaign_id`, and uses the same
`contact_id` and `fa_id` fields as `mock_client`. A campaign's name is read from
`mock_campaign`; it is not copied into every event. The earliest `contacted_at`
for an adviser, campaign, and client is that client's first recorded campaign
contact. Subsequent events represent later contacts with the same client.

Foreign keys require the event's adviser to be assigned to the campaign and to
own the client in the synthetic data. Both performance tools filter reads by the
request-scoped adviser's tenant and ID. This prototype history is not the
company's `interaction` table. The read-only
`get_campaign_contact_performance` tool reports one campaign's distinct
contacted-client counts; `get_campaign_contact_ranking` compares all accessible
campaigns by that same measure, including zero-contact campaigns and ties. The
API still accepts a caller-supplied FA ID, so this local prototype does not
provide production authentication.

## PULSE campaign email

The adviser can ask PULSE to draft or revise an email for a selected campaign.
The model supplies draft subject/body text to `prepare_campaign_email`; the
server recalculates criteria matches and filters them by tenant, adviser ownership
and `opt_in_email`. It stores the exact preview in `campaign_email_send` and
returns its included and excluded recipients plus an expiring phrase such as
`CONFIRM EMAIL ABC234`. Nothing is sent during preparation.

Only the exact phrase in the latest user message can invoke
`confirm_campaign_email`. The server rechecks campaign access, matching and
consent, then sends once per recipient through the configured transport. Local
development defaults to `EMAIL_DELIVERY_MODE=mock`, which simulates accepted
delivery without network access. Successful recipients each create a new
`mock_campaign_contact_event` row with `channel=email` and the batch ID, so
repeat outreach is retained while distinct-client performance counts remain
unchanged. Repeating the same confirmation returns the saved batch result and
does not send or log again.

`EMAIL_DELIVERY_MODE=gwm` selects the server-side GWM Core Email API adapter.
Its base URL, sender and any API key must remain in backend environment settings.
The supplied specification does not define authentication, rate limits,
idempotency or definitive application-level success codes, so live mode should
not be enabled until those details and a test endpoint are confirmed by the API
owner.

The schema follows the repository's rebuild convention rather than an in-place
migration. After pulling this change into an environment that already has the
old contact-event table, run `terraform destroy` from `backend/terraform`, then
run `make provision` from the repository root. This recreates the local tables
with email batch/channel fields and reloads the checked-in synthetic seed data.

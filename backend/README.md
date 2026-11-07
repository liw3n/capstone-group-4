# PULSE Chat API

For the free Render container, Supabase PostgreSQL and shared demo access, see the
[deployment runbook](docs/deployment.md). The root image serves React and runs
MCP on loopback; /live and /ready provide generic health checks. Startup performs
locked migrations because Free services have no pre-deploy hooks or shells.

FastAPI backend for the PULSE chat popup. The service calls Groq through its
OpenAI-compatible API, discovers and invokes tools through FastMCP over HTTP,
and persists sessions and messages in PostgreSQL.

Large recommendation results now stay in an adviser-scoped PostgreSQL snapshot;
chat/Groq receives at most 10 matches and 10 incomplete profiles, while Excel
downloads contain all results. `make provision` creates the snapshot table for
local copies; see [the recommendation guide](docs/campaign_recommendations.md#large-results-and-excel-downloads-7-november-2026).
Provisioning safely reapplies the existing campaign-member index without editing
the supplied CRM definitions or clearing data.

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
- `GET /campaign-drafts/{draft_id}?fa_id=<id>&session_id=<id>`
- `PATCH /campaign-drafts/{draft_id}`
- `POST /campaign-drafts/{draft_id}/regenerate`
- `POST /campaign-drafts/{draft_id}/preview`
- `POST /campaign-drafts/{draft_id}/confirm`

The campaign-draft routes also support matching `/api/...` forms. Only the final
confirmation route creates a campaign, always in `draft` status.

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

`get_active_campaigns` uses its own read-only tenant query: the frontend adviser
ID resolves the legacy chat tenant namespace, then campaigns are filtered by
`tenant_id`, non-deletion and status exactly `active`. Creator and schedule do
not narrow discovery; other tools keep their existing ownership/date rules.
The default table shows name, code, description, dates and readable age/gender/
cash criteria, including preset/custom combinations. Optional filters support
overlapping audience ranges, code/text search and schedule bounds. 'Over 40'
uses `age_min: 41`; a Male filter can include mixed-gender campaigns.
The chatbot renders the retrieved snapshot directly with today's Singapore date
and a working Excel link below the table. Browser export uses the displayed rows
and works after chat history reload. No extra endpoint, table, seed application
or configuration change is needed. SQL seed files are not runtime data sources.
See [the discovery contract](docs/api_contract.md#mcp-get_active_campaigns).

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
`campaign`. Stage 8 exposes adviser/session-scoped GET, PATCH and selected-
field regeneration routes at `/campaign-drafts/{draft_id}` (and matching `/api`
forms). Manual edits and model proposals both pass through the same selective-
revision validation boundary and optimistic revision check.

The frontend opens the artifact in a prefilled review mode inside the existing
Campaigns workspace. It shows rationale, assumptions, warnings and synthetic
catalogue provenance and supports editing, campaign schedule review and
multi-section regeneration.
The final preview is reloaded and policy-validated by FastAPI, then bound to the
current revision with a five-minute signed token. Only the token digest and
preview metadata are stored in the project-owned draft table. Set
`PULSE_CAMPAIGN_PREVIEW_SECRET` to a stable secret of at least 16 bytes in a
deployed environment; without it, a process-local random secret intentionally
invalidates outstanding previews after restart. Explicit confirmation now locks
and revalidates the latest revision and atomically inserts one row into the
unchanged official `campaign` schema with `status = draft`. The same transaction
marks the generation draft confirmed and persists its idempotency key and created
campaign ID. The UI exposes this as **Create draft campaign** only on the exact
server preview. Generation does not select named contacts, so it deliberately
does not write `campaign_member`; it also does not activate or send the campaign.
If an optimistic save is stale, the review reloads the latest scoped revision
in place rather than directing the adviser back through chat.

Campaign generation, MCP, HTTP and frontend code share the canonical targeting
values `under35`/`35to44`/`45to54`/`55to64`/`65plus`, lower-case
`male`/`female`, and `under50k`/`50kTo250k`/`250kTo1m`/`above1m`. The current
`campaign.audience_criteria` JSON uses hyphenated age/cash bands and title-cased
genders. `app/campaigns/criteria.py` converts those storage values at the
repository boundary; storage spellings are never added to the model-facing
generation schema. Contact gender is a separate CRM field and retains its own
representation.

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

## Synthetic campaign member and email performance

`make provision` creates and seeds `campaign` and `campaign_member`. The old
`mock_campaign_contact_event` history is no longer part of a fresh setup. The
read-only performance tools keep their existing MCP names for chat compatibility,
but their metrics now use only the remaining tables:

- `get_campaign_contact_performance` reports current member count, the number of
  members with `email_send_count > 0`, total recorded email sends, and the
  percentage of members with a recorded email. It also reports members **added**
  this week, last week, or in a named Monday–Sunday week in Singapore time.
- `get_campaign_contact_ranking` ranks adviser-owned campaigns by cumulative
  clients with a recorded email (default), or by members added in the chosen
  period. Weekly email ranking is unavailable. Ties and zero-count campaigns
  are included.

Member additions are not contacts. `campaign_member` has no event history for
repeat contacts, first contact, email delivery, or the week when each email was
sent. The tools therefore mark weekly contacted-client counts as unavailable
instead of returning a misleading zero or treating `added_at` as `contacted_at`.
Both tools restrict campaigns to the request-scoped adviser and tenant and count
only member rows added by that adviser. The API's adviser ID remains caller
supplied, so this prototype does not provide production authentication.

## PULSE campaign email

The adviser can ask PULSE to draft or revise an email for a selected campaign.
The model supplies draft subject/body text to `prepare_campaign_email`; the
server recalculates criteria matches and filters them by tenant, adviser ownership
and `opt_in_email`. Campaign names and IDs are resolved from the current turn or
recent adviser-authored chat context. The adviser supplies the sign-off name;
PULSE does not infer a name from an adviser identifier. The server stores the
exact preview in `campaign_email_send` and
returns its included and excluded recipients plus an expiring phrase such as
`CONFIRM EMAIL ABC234`. Nothing is sent during preparation.

Only the exact phrase in the latest user message can invoke
`confirm_campaign_email`. The server rechecks campaign access, matching and
consent, then sends once per recipient through the configured transport. Local
development defaults to `EMAIL_DELIVERY_MODE=mock`, which simulates accepted
delivery without network access. Successful outcomes create or update the
corresponding `campaign_member`, set `emailed_at`, increment
`email_send_count`, and increment the campaign's `email_send_runs` once for the
batch. `campaign_email_send` retains the reviewed content, recipient snapshot,
approval evidence and provider outcomes. The performance tools read stored
member counts and do not claim that they prove delivery.

`EMAIL_DELIVERY_MODE=gwm` selects the server-side GWM Core Email API adapter.
Its base URL, sender and any API key must remain in backend environment settings.
The supplied specification does not define authentication, rate limits,
idempotency or definitive application-level success codes, so live mode should
not be enabled until those details and a test endpoint are confirmed by the API
owner.

The schema follows the repository's rebuild convention rather than an in-place
migration. After pulling this change into an environment that already has the
old email table, run `terraform destroy` from `backend/terraform`, then
run `make provision` from the repository root. This recreates the local tables
with the official UUID relationships and reloads the checked-in synthetic data.

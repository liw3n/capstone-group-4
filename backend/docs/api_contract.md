# PULSE Chat API contract

## Hosted demo access and health

With `DEMO_AUTH_ENABLED=true`, assets and API routes (including direct and /api
aliases, OpenAPI and /health) require shared HTTP Basic credentials. Missing or
invalid credentials return 401 with WWW-Authenticate. Mutation requests require
an Origin matching the public request origin; absent/cross-origin values return
403. CLI clients must supply Origin too. This gate is not adviser identity.
Authenticated responses use Cache-Control: no-store.

`GET /live` is unauthenticated and returns `200 {"status":"ok"}`. `GET /ready`
is unauthenticated and performs a bounded PostgreSQL query and MCP tool discovery:
`200 {"status":"ok"}` or `503 {"status":"unavailable"}` within four seconds.
Neither exposes credentials or invokes Groq. Example:
`curl https://example.onrender.com/ready`.

Hosted React shares the API origin. Unknown API paths and missing assets return
404; browser navigation paths may fall back to index.html. Local authentication
is disabled by default. See deployment.md for settings and the legacy email gap.

All chat routes are also available with an `/api` prefix. Campaign routes
likewise support both `/campaigns/...` and `/api/campaigns/...`.

## `GET /health`

Returns API status, whether an LLM key is configured, and the configured model name.
It never returns the API key.

Example response:

```json
{"status":"ok","llm_configured":true,"llm_model":"openai/gpt-oss-20b"}
```

## Campaign catalogue and UI state

Campaign status accepts `draft`, `active`, `inactive`, `paused`, and `completed`.
`inactive` is preserved from the current synthetic seed; it is not treated as
active by discovery/matching. This avoids rejecting the whole campaign list
when an inactive row is present. Campaign confirmation still forces `draft`.

These endpoints use the synthetic PostgreSQL campaign catalogue as the source
of truth for both the CRM campaign screens and MCP campaign tools. They do not
provide production authentication: `role` and `fa_id` are supplied by the
prototype client, and the tenant is fixed to `pulse-demo`.

### `GET /campaigns?role=<advisor|marketing>&fa_id=<id>`

Returns campaigns newest first. `fa_id` is required for the adviser role; the
query returns only campaigns created by or assigned to that adviser. Marketing
receives marketing-origin campaigns and must omit `fa_id`. A storage failure
returns `503`.

### `GET /campaigns/{campaign_id}?role=<advisor|marketing>&fa_id=<id>`

Returns one campaign subject to the same role and adviser access predicate.
Unknown or inaccessible campaigns both return `404`.

### `POST /campaigns?role=<advisor|marketing>&fa_id=<id>`

Creates a synthetic campaign. The body is the complete frontend campaign model,
including criteria, resolved adviser routing, description, client copy,
lifecycle dates, lead statistics, and optional campaign-specific synthetic lead
records. The request `origin` must match `role`. Adviser-created campaigns are
assigned only to the supplied adviser.

Minimal contact-audience example:

```json
{
  "id": "campaign-demo-1",
  "name": "Synthetic review campaign",
  "status": "active",
  "startDate": "2026-10-12",
  "endDate": "2026-12-31",
  "description": "Internal synthetic campaign brief.",
  "clientMessage": "Educational outreach copy for adviser review.",
  "origin": "advisor",
  "audienceSource": "contacts",
  "teamIds": [],
  "advisorIds": [],
  "criteria": {"ageGroups": [], "genders": [], "cashBands": []},
  "includeIds": [],
  "excludeIds": [],
  "leadIds": [],
  "leadStats": {"uploaded": 0, "added": 0, "removed": 0},
  "createdBy": "Demo Adviser",
  "createdAt": "2026-10-12T00:00:00Z",
  "actions": {},
  "emailLog": [],
  "leadContacts": []
}
```

A duplicate ID returns `409`; role/origin mismatch returns `400`; invalid IDs,
date/range ordering, fields, or bounds return `422`; storage failure returns
`503`.

### `PATCH /campaigns/{campaign_id}/state?role=<advisor|marketing>&fa_id=<id>`

Persists mutable campaign UI state after a user interaction: `includeIds`,
`excludeIds`, `leadIds`, `leadStats`, `actions`, `emailLog`, and `leadContacts`.
It returns the complete saved campaign. Access is checked before the update;
missing or inaccessible campaigns return `404` and storage failure returns
`503`.

The email log records a user-confirmed **simulation**. Adviser updates are
rejected unless every recipient is an owned `mock_client` row with email consent;
Marketing cannot record adviser sends. The endpoint does not send a message,
write a production CRM interaction, or create a backend task.

### `POST /campaign/update-engagement-status?fa_id=<id>`

The API-prefixed route is `/api/campaign/update-engagement-status`. The plural
aliases `/campaigns/update-engagement-status` and
`/api/campaigns/update-engagement-status` are supported as well. This updates
the latest synthetic campaign event for one adviser-owned client. The JSON
body contains `campaign_id`, `contact_id`, and `status`: `0` is Contacted, `1`
is Engaged, and `2` is Rejected. If no event exists yet for that client and
campaign, the endpoint creates one. Campaign assignment and client ownership
are checked against the supplied adviser ID. A missing `fa_id` returns `400`,
an unknown or inaccessible campaign/client returns `404`, invalid identifiers
or status values return `422`, and database failures return `503`.

```json
{
  "campaign_id": "camp-1",
  "contact_id": "client-001",
  "status": 2
}
```

## CRM contacts

Contact routes support both direct and `/api`-prefixed forms. They expose
tenant/adviser-scoped synthetic `mock_client` records—the same IDs and matching
attributes used by campaign MCP tools. `fa_id` is required and remains a
caller-supplied prototype identity rather than authentication.

### `GET /contacts?fa_id=<id>`

Returns that adviser's contacts ordered by stable contact ID. For the untouched
seed, the demo adviser receives 12 rows; the other-adviser and other-tenant rows
are excluded in SQL. A storage failure returns `503`.

### `POST /contacts?fa_id=<id>`

Creates one synthetic contact. Core identity, targeting and consent fields are
stored as typed columns; optional CRM-only presentation data is stored in the
prototype JSONB extension. Duplicate IDs return `409`, invalid bodies return
`422`, and storage failure returns `503`.

### `PUT /contacts/{contact_id}?fa_id=<id>`

Replaces one contact after enforcing tenant/adviser ownership. The body ID must
match the path or the API returns `400`. Unknown and inaccessible contacts both
return `404`. The frontend uses this for contact edits and meeting summaries.

## `GET /chat/sessions?fa_id=<id>`

Returns the financial adviser's sessions in reverse chronological order.

`fa_id` is required and must not be empty. A storage outage returns `503`.

## `POST /chat/new?fa_id=<id>`

Creates and persists a new chat session.

Example response:

```json
{"session_id":"6efc8b88-6f67-4654-9d03-84e0cb741190","timestamp":"2026-10-03T00:00:00Z"}
```

## `GET /chat/history?session_id=<id>`

Returns the persisted user and assistant messages for a session.

A missing session returns `404`; a storage outage returns `503`.
Messages are ordered by timestamp and insertion order.

## `POST /chat/query`

Request body:

```json
{
  "fa_id": "advisor-123",
  "session_id": "optional-session-uuid",
  "message_content": "What actions are outstanding?"
}
```

`fa_id` may instead be supplied as a query parameter. If `session_id` is absent,
the latest session for the adviser is used or a new session is created. If it is
present, it must belong to the supplied adviser.

Response:

```json
{
  "user": "advisor-123",
  "timestamp": "2026-10-03T00:00:00Z",
  "ai_answer": "...",
  "campaignDraft": null,
  "campaignDraftOptions": null
}
```

`campaignDraft` is `null` for ordinary answers, clarification questions and
failed draft validation. After successful campaign generation or selective
revision it contains the complete server-validated structured draft, including
its stable `draftId`, `revision`, lifecycle status, objective, citations,
`changedFields`, validation warnings and `created: false`. Existing clients that
read only `ai_answer` remain compatible. Initial generation also returns the
explicitly clarified adviser-owned schedule under `creation.startDate` and
`creation.endDate`; those values are not model-authored draft fields.

`campaignDraftOptions` is normally `null`. When the adviser asks for
alternatives for one narrative field, it contains a persisted
`campaign_draft_options` object with `optionSetId`, `draftId`, `baseRevision`,
`field`, two to ten ordered `options`, `status`, `expiresAt` and `created: false`.
The option response does not change `campaignDraft` or its revision.

Provider or MCP tool-server failures are returned as `429`, `502`, `503`, or
`504` depending on the failure category. Groq receives schemas discovered from
the FastMCP server at `MCP_SERVER_URL`, filtered through an explicit list of
model-discoverable tools. The model cannot invoke a tool absent from that turn's
offered list. A response asking for such a tool is rejected before any tool in
that response is run. Email confirmation, campaign-draft preparation and draft
revision are server-routed paths, not ordinary model-callable tools. A separate
system instruction treats chat history, CRM text, retrieved references and tool
results as untrusted data; it does not grant those sources authority to change
scope or confirmation rules. Tool execution is bounded by
`LLM_MAX_TOOL_ROUNDS`.

These are prototype guardrails, not authentication. The API still accepts a
caller-supplied `fa_id`; a real deployment must derive adviser and tenant
identity from a verified login before relying on the storage scope checks.

After a successful provider response, the user and assistant messages are stored
in one PostgreSQL transaction. When the response carries a draft artifact, its
insert or optimistic revision update occurs in that same transaction. A failed
provider request or stale draft update does not append a partial exchange,
although a session explicitly created beforehand remains.

For a clear but underspecified campaign-generation request, the server responds
with at most three server-selected clarification questions before reference
retrieval or draft generation. The hybrid interpreter first normalizes common
punctuation and known phrases. When material questions remain, a separate strict
JSON-schema model call extracts only planning focus, audience presence, explicit
targeting intent and an explicitly stated schedule. The server then validates
that untrusted extraction against the supported enums and date-ordering rules
and makes the final readiness decision. The model cannot add a targeting band,
mark an unsupported band as valid or invent a missing campaign date or duration.

When readiness is reached, the server materialises the resolved age, gender and
cash values as a targeting lock. Explicit adviser selections and unrestricted
defaults are both included. The lock is supplied to structured draft generation
so the model can write consistent copy, and the server overwrites the generated
`draft.criteria` with the locked values before calling
`prepare_campaign_draft`. The existing targeting-text validation still rejects
a demographic summary or rationale that contradicts those locked criteria.
The server separately locks the resolved schedule and carries it to persistence
as adviser-owned creation metadata; the schedule is never added to the
model-generated `draft` object.

The active flow is stored in PostgreSQL against the fixed tenant, supplied
adviser and resolved chat session. The next message in that session is treated
as the answer and reassessed; a new campaign request replaces the pending flow.
`cancel campaign draft` discards it. After three unresolved answer rounds, the
flow closes with a safe explanation. Only the objective and clarification
answers are supplied to intent extraction; no client or campaign records are
included.

Material life-stage terms such as `students`, `young`, `early-career` or
`entering the workforce` require an explicit age choice before they can become
an age criterion. An explicit value such as `Under 30` remains unresolved because
it is not one of the supported age bands; the interpreter cannot silently round
it to `Under 35`. Undefined cash terms such as `high-value` require a threshold.
For conflicting explicit values, the latest clarification answer takes precedence.
An absent gender or cash restriction is recorded in the canonical objective as
unrestricted and locked as an empty criteria list rather than inferred. Both
campaign dates are material: if neither is present the server asks for both, if
one is present it asks only for the missing date, and an end date before the
start date is rejected. `use safe defaults` may resolve targeting but never
supplies a schedule. While questions remain, no MCP retrieval,
draft generation, draft persistence or campaign creation occurs. A bounded
intent-extraction call may occur. The response
continues to use the existing `ai_answer` string, so both route forms remain
backward compatible.

After a validated draft exists in the same scoped chat session, a request that
explicitly names one or more supported fields can be routed to selective
revision before new-campaign generation. For example, “generate a more unique
campaign name” revises only `name`; “rewrite the campaign name and description”
revises both in one operation. Supported fields are `name`, `description`,
`clientMessage`, `ageGroups`, `genders`, `cashBands` and
`targetDemographicSummary`. Ambiguous requests ask which fields to revise.

The chat session stores the active draft ID. A broad, scoped gate recognises
field/value phrasing whenever that pointer exists, including declarative and
compact instructions that omit the words `campaign` and `draft`. Before handling
such a turn, the server resolves a strict action: ordinary chat, revise named fields,
suggest alternatives, select a numbered alternative, show the current draft,
start a new draft, or ask for clarification. Deterministic rules handle clear
phrasing, with a schema-constrained model classifier as a bounded fallback.
Starting new generation while a draft is active requires explicit new/separate/
replacement intent. “Please draft the full campaign” therefore renders the
current structured draft without changing it. Ordinary discovery, matching,
follow-up, performance and campaign-email intents have precedence, remain on
their existing MCP tool path and do not load the active draft.

For example, “give me five more unique campaign name options” returns a
revision-bound option set. “Let's try the fifth option” resolves against that
stored set, proposes exactly its fifth value for `name`, and invokes the same
selective revision boundary. Option sets are tenant/adviser/session/draft scoped,
expire after 15 minutes, and are marked stale after any successful revision.
Missing, expired, out-of-range and stale selections do not modify the draft.

The server loads the session's active draft by tenant, adviser and session
(falling back to the latest reviewable draft only for pre-pointer rows), sends
the model only that structured draft and a selected-field-only schema, and
injects the objective, citations and current revision when invoking
`revise_campaign_draft`. The complete result is revalidated and stored against
the same `draftId` at revision `n + 1`; unselected independent fields cannot be
overwritten. When age, gender or cash criteria change, the server derives the
demographic summary and field-level rationale as dependent metadata. Chat and
regeneration revisions also request consistent description and client-message
copy using any explicitly resolved targeting as authoritative context. Explicit
targeting values in the adviser instruction are normalized and locked to
supported enums after model output, so the model cannot substitute a different
band. Generated drafts still use fixed bands: `above 65` maps to
`65plus`, while `more than 250k` maps to both `250kTo1m` and `above1m`. Because
those bands include the boundary values, the returned validation warnings make
the approximation visible for adviser review.
Repeated turns therefore support multiple sequential revisions. Generation and
revision write chat and campaign-generation review tables only; neither writes
`campaign`. Option creation and selection are committed atomically with the
matching chat exchange; selection and the resulting optimistic revision share
one transaction.

Example:

```bash
curl -X POST http://localhost:4000/chat/query \
  -H 'Content-Type: application/json' \
  -d '{"fa_id":"advisor-123","message_content":"Add 12.5 and 7.5"}'
```

### Error responses

- `400`: neither the body nor query string supplies `fa_id`.
- `404`: the selected session does not exist or belongs to another adviser.
- `409`: a campaign draft revision is stale and cannot overwrite newer work.
- `422`: request validation failed or the stripped message is empty.
- `429`: the upstream model provider rate-limited the request.
- `502`: provider authentication, response, or tool-loop failure.
- `503`: LLM configuration or PostgreSQL is unavailable.
- `504`: the upstream model request timed out.


## Campaign context and synthetic recommendation tool

The PULSE web frontend identifies campaigns through the adviser's chat message.
It sends adviser/session/message fields only; opening a campaign in the CRM
does not supply campaign context or reset the conversation. The LLM can request
`resolve_campaign` and then recommendations, or ask for a campaign name when
none is identified. The previous selected-campaign banner/shortcut is removed.

`POST /chat/query` and `POST /api/chat/query` additionally accept an optional
`campaign_id` for backwards-compatible API clients (1-69 letters, digits, hyphens
or underscores; starts with a letter or digit). The web chat does not send this
field. Explicit API-client example:

```json
{
  "fa_id": "adv-steven-raynaldi",
  "campaign_id": "camp-1",
  "message_content": "Which clients are recommended for this campaign?"
}
```

Omitting it preserves existing chat behavior. An invalid ID returns `422`;
an unknown/inaccessible campaign returns `404`; a campaign that is not active
on today's Asia/Singapore date returns `409`. Start/end dates are inclusive and
status must be `active`. Campaign validation happens before session
creation/provider calls. The backend retrieves criteria from its synthetic
PostgreSQL repository; the request never supplies campaign criteria. Missing
database configuration, tables or database availability return `503` during
campaign validation, before chat storage/provider calls.

The API binds an immutable adviser/tenant scope to each orchestration call. The
MCP client supplies it as `_meta.pulse_scope`, separate from model arguments.
No request-specific state is stored on the cached orchestrator. `fa_id` remains
caller-supplied and the tenant is fixed to `pulse-demo`; this is not authentication.

### MCP: recommend_clients_for_campaign

Arguments: `campaign_id` (required) and `limit` (strict integer, 1-100, default 100).
Context is injected by FastMCP and absent from the model-facing schema. This is
the pre-contact audience tool: use it to find or filter potential clients who
meet campaign eligibility criteria. It returns synthetic criteria matches,
without ranking, checking reply status, sending outreach or changing CRM data.

Result keys: `data_source`, `campaign_id`, `campaign_name`, `as_of_date`,
`evaluated_count`, `matched_count`, `clients` (contact_id, name, reasons),
`returned_count`, `truncated`, `incomplete_count`, `incomplete_clients`
(contact_id, name, missing_fields), `incomplete_truncated`, `excluded_count`
and `disclaimer`. Counts refer only to that adviser's tenant-scoped book.

Domain failures return `data_source: synthetic`, `error` and `error_code`
(`missing_context`, `campaign_unavailable`, `campaign_inactive`, or
`storage_unavailable`). Database errors do not return client lists or connection details. Invalid
arguments are rejected by the API-side argument model or MCP input validation.
Tool errors are passed back to the LLM as errors, never successful audience results.
Recommendations are not communication consent or product suitability approval.

### MCP: campaign_follow_up

This is the post-contact follow-up tool: it finds clients already contacted for
the campaign who have no recorded reply/response. Do not use it for pre-contact
audience discovery or criteria filtering.

Model-facing arguments: `campaign` (optional campaign name or ID from the
current user message) and `limit` (integer 1-100, default 5). When the API
request includes a selected `campaign_id`, that server-bound context takes
precedence over the model argument; otherwise the campaign from the current
message is used. The API supplies the adviser identity through
`_meta.pulse_scope`; `fa_id` is not a model argument and is never requested
from the adviser by the assistant. The tool uses that scoped adviser ID when
retrieving unreplied clients. Each candidate includes a `follow_up_reason`
based on the latest contact date and the absence of a recorded response. The
assistant should give that factual reason for each candidate; profile and
portfolio details are context only, not evidence of suitability, priority or a
campaign-specific need.

See [campaign_recommendations.md](campaign_recommendations.md) for fake table
assumptions, shared Make setup, expected frontend results and automated tests
that work without Groq.

### MCP: find_campaign_references

This read-only, non-destructive tool is the implemented retrieval boundary for
campaign generation. It searches a checked-in catalogue of approved synthetic
campaign patterns. It does not read client or campaign tables, create a campaign,
select an audience, assess suitability or send outreach.

Model-facing arguments are `objective` (required, 10-2,000 characters), optional
`categories` (up to five values from `retirement`, `protection`, `education`,
`legacy`, `property`, `other`) and `limit` (strict integer 1-3, default 3).
`fa_id`, `tenant_id` and MCP context are forbidden arguments. The API supplies
adviser and tenant scope through `_meta.pulse_scope`.

The service filters tenant access, approval state and the Singapore-date validity
window before applying transparent category, objective-tag and bounded lexical
scoring. Ties use stable reference ID and version ordering. An irrelevant
objective returns a successful empty result rather than a fabricated match.

Successful results contain `type: campaign_references`,
`data_source: synthetic_curated_catalogue`, the query, catalogue version, a
short-lived `retrievalToken`, up to three references, `returnedCount` and
`truncated`. Each reference includes its stable ID and version, category,
matched tags, match reasons, approved description and messaging patterns,
typical criteria, targeting rationale and required disclaimers. Tenant allowlists
and prohibited-claim governance fields stay server-side.

The HMAC-signed retrieval token binds the normalized objective hash, adviser and
tenant scope, catalogue version, returned reference IDs and versions, issue time
and expiry. Later draft preparation must reject altered, expired, cross-scope or
stale tokens. The local fallback signing key is process-scoped, so a FastMCP
restart invalidates outstanding tokens; deployments may provide
`PULSE_CAMPAIGN_RETRIEVAL_SECRET`.

Safe failures use `missing_context`, `invalid_arguments` or
`catalogue_unavailable` and never expose parser details, file paths or secrets.

### MCP: prepare_campaign_draft

This read-only, non-destructive tool validates and packages one model-generated
campaign proposal. It must be called after `find_campaign_references`; it never
inserts a draft or campaign row, changes campaign status, selects clients,
activates outreach or sends a communication.

Direct MCP arguments are the original `objective`, the returned
`retrievalToken`, up to three `referencesUsed` citations containing only
`referenceId` and `version`, and one strict `draft`. The draft contains name,
description, client message, age/gender/cash criteria, demographic summary,
field-level rationale, assumptions and disclaimer. Unknown fields and unsupported
enum values are rejected. Adviser and tenant scope remain trusted MCP metadata,
not tool arguments.

For clear API-orchestrated campaign-generation requests, the server identifies
the intent and calls reference retrieval before draft inference; the model does
not author either MCP call. Draft inference uses strict JSON Schema output
without tools and supplies only `referencesUsed` and `draft`; the request-scoped
registry injects the exact retained objective and token before the server calls
preparation. This removes provider failures caused by malformed retrieval or
nested preparation calls. Inference receives the current objective and bounded
reference fields, but not the signed token or prior tool-call protocol messages.
The direct MCP contract still requires all four arguments.

The handler verifies the token signature, expiry, objective hash, adviser and
tenant scope, catalogue version and allowed citation set. `referencesUsed` must
be a subset of the exact retrieval result; an empty retrieval result permits only
an empty citation list.

Deterministic policy checks reject guarantees, risk-free or regulatory-approval
claims, invented percentage claims, instructions that bypass adviser review,
email addresses, phone/identity/account identifiers, insufficient educational
and individual-review language, and targeting text that contradicts the
structured criteria. Cited catalogue-specific prohibited claims are also
enforced. Ambiguous terms, unsupported demographic restrictions and material
assumptions become concrete adviser-review warnings rather than numeric model
confidence scores.

Missing educational, non-advice or individual-review wording is repaired before
policy validation: the server appends a standard notice only to each incomplete
`clientMessage` or `disclaimer` field and adds a concrete validation warning.
The model-authored content remains intact, the addition is visible in the
returned draft, and adviser review is still required. This omission therefore
does not normally produce a blocking `missing_disclaimer` response.

The guarantee, risk-free, regulatory-approval and catalogue phrase checks are
negation-aware: explicit warnings such as "returns are not guaranteed" are
allowed, while affirmative claims remain blocked. Numeric percentage or currency
claims remain blocked even when negated because the figure itself is ungrounded.
An unsupported-claim error may include a safe `field` path and `rule` identifier
without echoing the generated sentence.

A successful result has `type: campaign_draft`, `data_source: ai_generated`, the
objective, exact citations, validated draft, `validation` with
`schema_valid: true`, `policy_valid: true` and warnings,
`requires_adviser_review: true`, and `created: false`. No draft ID, revision,
campaign status, creator or timestamp exists in the MCP result because the tool
does not persist. FastAPI adds the server-owned draft ID and revision only after
validating and storing the artifact.

Safe failures use `missing_context`, `invalid_draft`,
`invalid_retrieval_token`, `expired_retrieval_token`, `scope_mismatch`,
`invalid_reference_citation`, `unsupported_claim`, `missing_disclaimer`,
`inconsistent_targeting` or `catalogue_unavailable`. They do not echo unsafe
draft text, secrets, parser details or storage information.

The chat system prompt requires reference retrieval before preparation and
prohibits claiming that a returned proposal was created, approved, activated or
sent. After successful preparation, the orchestrator validates the returned
artifact again, stops the model loop and deterministically renders every field
as Markdown. The stored `ai_answer` therefore includes the description and all
other draft sections without relying on a model-authored summary. Stage 7 also
persists the structured artifact and returns it as `campaignDraft`; this API-side
write does not change the read-only MCP tool.

### MCP: revise_campaign_draft

This read-only, non-destructive Stage 6 tool validates a selective revision of
an existing validated campaign draft. It does not persist a draft, create or
update a campaign, select clients, activate outreach or send communications.

Arguments are the original `objective`, existing `referencesUsed`, authoritative
`currentDraft`, `revision`, an optional adviser `instruction`, one to seven
selected `fields`, and `proposedChanges`. Supported fields are `name`,
`description`, `clientMessage`, `ageGroups`, `genders`, `cashBands` and
`targetDemographicSummary`. `proposedChanges` must contain exactly the selected
fields; extra, missing, duplicate, null or unsupported changes are rejected.
Age, gender and cash changes are merged into the nested criteria object.

The handler resolves cited catalogue entries only when they remain approved,
valid and available to the request tenant. It revalidates the current draft,
applies only the selected changes, restores every other independent supported
field and reruns disclaimer, unsupported-claim, personal-data and targeting-
consistency checks. Criteria revisions deterministically refresh the complete
field-level rationale and, when it was not explicitly selected, the demographic
summary. This derived metadata cannot retain an obsolete unrestricted-audience
claim after age, gender or cash criteria change.

A successful result has `type: campaign_draft_revision`, `data_source:
ai_generated`, the objective and citations, the complete validated draft,
`previousRevision`, `revision` incremented by exactly one, `changedFields`,
validation results, `requires_adviser_review: true` and `created: false`.
Failures use the existing safe campaign-generation error codes and do not echo
unsafe generated text.

The tool is exposed directly by FastMCP but remains omitted from the generic
model-facing tool list. For a recognised chat revision request, the Stage 7
orchestrator loads the authoritative persisted artifact, asks the model through
a strict selected-field-only schema, and invokes this tool directly with the
server-held objective, citations, draft and revision. Stage 8 uses the same
boundary for both structured manual edits and selected-field regeneration from
the editable Campaigns review experience.

### Campaign draft review

Every route below is available both with and without the `/api` prefix. Drafts
are review artifacts, not campaign records. Review, revision and preview
endpoints never write the official `campaign` or `campaign_member` tables. Only
the explicit confirmation endpoint creates one inactive `campaign` row; none of
these endpoints selects a named audience, activates outreach or sends messages.

`GET /campaign-drafts/{draft_id}?fa_id=<adviser>&session_id=<session>` returns
the current `campaign_draft` artifact only when it belongs to that adviser and
chat session and remains in `generated` or `reviewed` state. Missing,
cross-adviser and cross-session drafts return `404` without disclosing which
condition failed; a scoped draft in a non-reviewable lifecycle state returns
`409`.

`PATCH /campaign-drafts/{draft_id}` applies one or more exact adviser edits:

```json
{
  "fa_id": "advisor-123",
  "session_id": "session-uuid",
  "expectedRevision": 1,
  "changes": {
    "name": "Clearer retirement check-in",
    "cashBands": ["50kTo250k"]
  },
  "creationChanges": {
    "startDate": "2026-11-10",
    "endDate": "2027-01-31"
  }
}
```

Supported change keys are `name`, `description`, `clientMessage`, `ageGroups`,
`genders`, `cashBands` and `targetDemographicSummary`. At least one non-null
change is required. The server invokes `revise_campaign_draft` with the stored
objective, citations and current artifact, reruns complete policy validation,
preserves every unselected field and stores the next revision as `reviewed`.
For a manual criteria edit, `targetDemographicSummary` and rationale are updated
as dependent metadata; `changedFields` includes the demographic summary.
`creationChanges` accepts adviser-owned `startDate` and `endDate`. Date-only
updates do not invoke the model, but they still advance the optimistic revision,
invalidate any prior preview and reject an end date before the start date.

`POST /campaign-drafts/{draft_id}/regenerate` asks the model to propose values
for only the selected independent fields, then passes the proposal through the
same trusted revision boundary. Selecting an age, gender or cash field also
regenerates description, client message and demographic summary so visible copy
does not continue describing the previous audience:

```json
{
  "fa_id": "advisor-123",
  "session_id": "session-uuid",
  "expectedRevision": 2,
  "fields": ["description", "clientMessage"],
  "instruction": "Make these sections warmer and more concise."
}
```

`fields` must contain one to seven unique supported fields, and `instruction`
must be non-empty. Both mutation routes return the complete persisted artifact
with the same `draftId`, revision advanced exactly once, `status: reviewed`,
and `changedFields`. A stale expected revision returns `409`; invalid request or
policy content returns `422`; unavailable storage returns `503`; regeneration
may also return `429`, `502` or `504` for provider failures.

`GET /chat/sessions` includes nullable `active_campaign_draft_id`. The frontend
uses this pointer to restore the current structured draft rather than parsing
assistant prose. On a `409` save/regeneration conflict, the frontend reloads the
latest scoped revision and asks the adviser to review it before continuing.

#### Final preview and campaign creation

`POST /campaign-drafts/{draft_id}/preview` reloads the scoped current revision,
resolves every cited catalogue entry again, reruns deterministic policy
validation and hashes the exact draft, reviewed creation metadata and validation
result. Both start and end dates must be present. Request:

```json
{
  "fa_id": "advisor-123",
  "session_id": "session-uuid",
  "revision": 3
}
```

The response contains the exact content the frontend must display and a
five-minute HMAC-signed confirmation token bound to the tenant, adviser, session,
draft ID, revision and content hash:

```json
{
  "type": "campaign_draft_preview",
  "draftId": "11111111-1111-4111-8111-111111111111",
  "revision": 3,
  "contentHash": "64-lowercase-hex-characters",
  "confirmationToken": "signed-token",
  "expiresAt": "2026-10-31T08:05:00Z",
  "draft": {},
  "creation": {
    "startDate": "2026-11-10",
    "endDate": "2027-01-31",
    "audienceSource": "contacts"
  },
  "validation": {
    "schema_valid": true,
    "policy_valid": true,
    "warnings": []
  },
  "requires_adviser_review": true,
  "created": false
}
```

Only the SHA-256 digest of the token is stored in
`campaign_generation_drafts`; issuing a newer preview supersedes the previous
token. Any successful edit or regeneration advances the revision and clears
all stored preview metadata. Deployments should set a stable secret of at least
16 bytes in `PULSE_CAMPAIGN_PREVIEW_SECRET`; otherwise a random process-local
secret is used and outstanding tokens stop working after a restart.

`POST /campaign-drafts/{draft_id}/confirm` is the explicit consequential action.
It verifies that the exact server-issued preview remains current and then creates
one campaign. Request:

```json
{
  "fa_id": "advisor-123",
  "session_id": "session-uuid",
  "revision": 3,
  "confirmationToken": "signed-token",
  "idempotencyKey": "confirm-browser-generated-uuid"
}
```

The response is the stored `CampaignPayload`; its essential creation fields are:

```json
{
  "id": "22222222-2222-4222-8222-222222222222",
  "name": "Clearer retirement check-in",
  "status": "draft",
  "startDate": "2026-11-10",
  "endDate": "2027-01-31",
  "origin": "advisor",
  "audienceSource": "contacts",
  "createdByAdvisorId": "advisor-123"
}
```

The server locks the scoped draft, revalidates its citations and policy, checks
the revision, stored token digest, signature and expiry, and inserts the official
`campaign` row with server-forced `status: draft`. In the same PostgreSQL
transaction it marks the project-owned generation draft `confirmed`, records the
created campaign ID, confirmed revision/time and idempotency key, and clears the
session's active-draft pointer. Repeating the request with the same key returns
the same campaign; a conflicting repeat returns `409`.

Adviser ownership is represented by official
`campaign.created_by_user_id`. Confirmation does not write `campaign_member`:
that official table represents named contact membership, and this workflow has
not selected or consent-filtered named contacts. Confirmation also does not
activate the campaign or send communication.

Missing, cross-adviser and cross-session drafts return `404`. Stale revisions,
missing previews, altered tokens and superseded previews return `409`; expired
previews return `410`; invalid request shapes or policy failures return `422`;
catalogue/configuration or storage failures return `503`.

### Campaign generation contracts and ownership

Stages 1-10 define generation, selective revision, review-only draft persistence,
the editable review experience, a server-verified final preview and explicit
creation of an inactive campaign.
The lifecycle values are `generated`, `reviewed`, `confirmed`, `rejected` and
`expired`. MCP preparation and revision remain read-only and return unpersisted
artifacts. The FastAPI host validates those artifacts again and stores the
current review-only state in `campaign_generation_drafts`, scoped by tenant,
adviser and chat session. The chat session's active-draft pointer identifies the
review context, while `campaign_generation_draft_options` stores short-lived,
revision-bound narrative choices separately from chat prose. Stage 9 stores only
the final preview hash, revision, token digest and timestamps in the project-owned
draft table. Stage 10 adds adviser-reviewed creation metadata, confirmation audit
fields, the idempotency key and created-campaign linkage without altering the
official campaign schemas.

Campaign targeting uses the same canonical values in chat artifacts, draft
review endpoints, MCP arguments and frontend payloads:

- `ageGroups`: `under35`, `35to44`, `45to54`, `55to64`, `65plus`;
- `genders`: `male`, `female`; an empty array means unrestricted;
- `cashBands`: `under50k`, `50kTo250k`, `250kTo1m`, `above1m`.

These public values intentionally differ from the current prototype campaign
table's JSON spellings (`35-44`, `Male`, `50k-250k`, and similar). The backend
converts those values at the storage boundary. Storage-only spellings are not
valid draft, MCP or HTTP criteria values and are not included in model-facing
JSON schemas. Contact-profile gender is a separate CRM field and continues to
use its own API representation.

Pre-generation clarification has its own implementation lifecycle (`active`,
`completed`, `cancelled`) and is not a campaign draft lifecycle state. It stores
only the objective, adviser answers and pending question IDs in
`campaign_generation_clarifications`; it never writes `campaign`.

- Model-generated, adviser-reviewable content: campaign name, description,
  client message, demographic summary, field-level rationale, assumptions and
  disclaimer.
- Server-owned during initial generation: the resolved age groups, genders and
  cash bands. Later review/edit stages may change them explicitly, but the
  generation model cannot replace them.
- Adviser-owned creation metadata: start and end dates are explicitly supplied
  or clarified before initial generation, stored separately from model-authored
  content, and remain editable in review. Audience source remains `contacts` in
  this prototype.
- Server-owned content: tenant and adviser ownership, draft and campaign IDs,
  revision and lifecycle state, campaign status, creator, timestamps, hashes,
  signing tokens and idempotency state.

Model-facing contracts reject unknown fields and cannot accept tenant, adviser,
campaign status, creator or creation timestamps. The existing campaign status
constraint already supports `draft`, but stages 1-4 do not write campaigns or
change the current activation behavior. A later confirmation path must force
`status = draft` on the server.


### MCP: get_active_campaigns

This read-only tool uses the existing MCP endpoint. It adds no REST route, SQL
schema, startup migration, port or provisioning step. Recommendation, lookup,
performance, follow-up, generation and email behavior remain unchanged.

The API carries the frontend `fa_id` through MCP `_meta.pulse_scope`, separately
from model-authored arguments. Discovery resolves the legacy `pulse-demo` tenant
namespace to that request's adviser UUID. An explicit server tenant stays
explicit. Its dedicated repository query filters `campaign.tenant_id`,
`is_deleted = FALSE` and `status = 'active'`. It does not require creator ownership;
another creator in the same tenant is included. Other tools retain their existing
adviser ownership predicates. Caller-supplied adviser identity is a prototype
boundary, not authentication.

Active status is independent of the schedule. Future, expired or undated active
rows remain discoverable; null, inactive, draft, paused and deleted rows are
excluded. Today's actual Asia/Singapore date is reporting context only. This
does not change recommendation eligibility. Campaign name lookup and matching
both use today's Singapore date for schedule checks; matching uses one captured
date for activity, client ages and the returned `as_of_date`.

Arguments:

- `campaign_ids`: optional exact IDs, at most 100.
- `campaign_names`: optional case-insensitive exact names, at most 100.
- `fields`: optional output columns, 1–14 entries.
- `limit`: strict integer 1–1000, default 1000.
- `filters`: optional validated restrictions below.

IDs/names intersect when both are supplied. An empty selection list returns no
rows. A CRM-selected campaign or earlier conversation does not narrow a general
listing. Campaign name is always present; columns are deduplicated in requested
order. Defaults are `name`, `campaign_code`, `description`, `start_date`,
`end_date`, `age_groups`, `genders`, `cash_bands`. Additional selectable fields:
`campaign_id`, `age_min`, `age_max`, `cash_min`, `cash_max`, `status`.

Supported filters:

- `age_min`, `age_max`: strict integers 0–130.
- `genders`: Male and/or Female.
- `cash_min`, `cash_max`: finite nonnegative numbers.
- `cash_min_exclusive`, `cash_max_exclusive`: booleans, false by default.
- `campaign_codes`: case-insensitive exact codes, at most 100.
- `name_contains`, `description_contains`: case-insensitive substrings.
- `start_date_from`, `start_date_to`, `end_date_from`, `end_date_to`: ISO dates.

Unknown keys, reversed ranges and inconsistent exclusive bounds are rejected.
Output projection and filtering are independent. For example, 'over 40' sets
`age_min: 41`, 'at least 40' sets `age_min: 40`, and 'under 40' sets `age_max: 39`.
Strict cash comparisons use the corresponding exclusive flag.

Audience filters use overlap semantics: AND across dimensions and OR across a
campaign's preset/custom alternatives in a dimension. Unrestricted dimensions
accept any requested value. A Male filter also matches mixed-gender and
unrestricted campaigns; there is no exact/exclusive-audience mode. Preset cash
intervals are lower-inclusive/upper-exclusive; custom endpoints are inclusive.
No client records are read for discovery filtering.

Audience JSON supports storage presets (`35-44`, `50k-250k`, title-case genders),
existing canonical aliases, and `ageCustomMin`, `ageCustomMax`, `cashCustomMin`,
`cashCustomMax`. Custom and preset restrictions can coexist. Full original
criteria are displayed with readable labels and 'or' between alternatives.
Empty restrictions display 'Any'; absent dates display 'Unknown'. Malformed
stored criteria return a safe storage error instead of silently widening scope.

Output keys are `data_source: synthetic`, `as_of_date`, `filters`, `columns`,
`rows`, `table`, `total_count`, `returned_count`, `truncated`, `disclaimer`.
Filters apply before counting/limiting. Invalid arguments, missing context and
storage failures use `invalid_arguments`, `missing_context`, `storage_unavailable`;
no credentials, raw SQL errors or fallback fixtures are returned.

The MCP wrapper calls `execute_get_active_campaigns` in `app/tools/discovery.py`.
The orchestrator renders the returned snapshot directly with
`render_active_campaigns`, without a subsequent model summary. It shows the
current Singapore date above the escaped Markdown table, an optional filter
summary explaining overlap semantics, and
`[Download Excel (.xlsx)](#active-campaigns-excel)` below it. Empty results are
explicit; truncated results state displayed and total counts. Synthetic source
metadata is retained without adding a routine demo notice to every listing.

The assistant-message renderer associates the download marker with its preceding
table, including after saved chat history reload. `lib/campaignExport.ts` creates
`active-campaigns.xlsx` in the browser with an 'Active Campaigns' sheet containing
exactly the displayed columns/order/rows. No second database request or export
endpoint is used. The Excel writer is bundled with the page so clicking the
link does not fetch a separate lazy JavaScript chunk, which can be unavailable
after a deployment or due to an asset/network failure. Workbook generation and
the browser download start in the click's synchronous execution path. Temporary
links/object URLs are cleaned up even if the browser rejects the download.
Formula-like strings remain text. A marker without a table
shows an unavailable fallback. Existing Markdown safety restrictions remain.

Example arguments:

```json
{"filters":{"age_min":41,"genders":["Female"],"cash_min":250000,"cash_min_exclusive":true}}
```

This is campaign discovery, not client matching, suitability assessment or consent
approval. It does not send communications, mutate CRM data, create tasks or
measure outcomes. Those remain separate existing operations.

### MCP: resolve_campaign

Read-only identity lookup, separate from campaign catalogue presentation.
Argument: `campaign_name`, a trimmed non-empty string of at most 255 characters.
Adviser/tenant scope is supplied in `_meta.pulse_scope`, never model arguments.
It shares discovery's scoped active-campaign query and Singapore reporting date;
it does not retrieve clients, check consent, send communications or mutate CRM.

Exact normalised names take precedence over partial names. Case/punctuation
differences, a conversational leading "the" or trailing "campaign", and whole-word
partial phrases are accepted. Typographical similarity is not guessed. The result
contains `data_source: synthetic`, `as_of_date` and one of:

- `status: matched`, with `campaign_id` and canonical `name`.
- `status: ambiguous`, with `candidate_count`, up to five `candidates` (ID/name),
  `truncated`, and a clarification message. There is no chosen top-level ID.
- `status: not_found`, with `candidate_count: 0` and a message. Inaccessible and
  inactive records are indistinguishable from unknown names.

Missing scope, invalid arguments and database failures return safe structured
errors using `missing_context`, `invalid_arguments` and `storage_unavailable`.
For example, `{"campaign_name":"first home starter bundle campaign"}` can resolve
to `{"status":"matched","campaign_id":"b2222222-2222-2222-2222-222222222222",
"name":"First Home Starter Bundle",...}` using the current synthetic seed.

The LLM chooses `resolve_campaign`, receives its result, and may request
`recommend_clients_for_campaign` with that ID. `tool_choice="auto"` is retained.
The registry validates and executes only requested calls; no backend sequence
forces lookup or recommendations. Known IDs may be used directly; ambiguity
requires the adviser to choose a campaign name. Older assistant requests for
internal IDs are not instructions to repeat that behaviour.

### MCP: get_campaign_contact_performance

This read-only tool retains its legacy name for chat compatibility. It now reads
only `campaign` and `campaign_member`. Model-facing arguments are optional
`campaign` (exact name or ID), optional `period` (`this_week`, `last_week`,
or `specific_week`), and `week_of` (a `YYYY-MM-DD` date required only for
`specific_week`). Weeks are Monday-Sunday in Singapore time. A selected
`campaign_id` from server metadata takes precedence over a model-provided name.

The API supplies adviser and tenant scope through `_meta.pulse_scope`. The
database checks that the campaign belongs to that adviser and tenant, and
counts only active member rows added by that adviser. Result fields include
`campaign_members_total`, `clients_emailed_total` (members with
`email_send_count > 0`), `email_sends_total` (sum of that stored count),
`email_coverage_percent`, `members_added_this_week`, and
`members_added_last_week`. A named week also returns
`members_added_requested_week` and its start/end dates. The result includes
`contact_history_available: false` and `weekly_email_history_available: false`.

Example tool arguments:

```json
{"campaign":"First Home Starter Bundle","period":"specific_week","week_of":"YYYY-MM-DD"}
```

`added_at` measures when a client joined a campaign. It is not a contact date.
The remaining schema cannot determine clients contacted in a given week,
first-contact dates, repeat contacts, or the week in which each email was sent.
The tool therefore does not return the old `contacted_clients_*` fields.
Stored email counts are cumulative snapshot values and do not prove delivery.
The tool returns structured errors for invalid periods, missing or inaccessible
campaigns, missing context, and unavailable storage. The request adviser ID is
caller supplied in this prototype, so it is not production authentication.

### MCP: get_campaign_contact_ranking

This read-only tool also retains its legacy name. It compares all campaigns
owned by the scoped adviser in the tenant, including zero-count campaigns and
ties. Its optional `metric` is `clients_emailed` (default, cumulative members
with `email_send_count > 0`) or `members_added` (member rows added in the
chosen period). Its optional `period` is `campaign_to_date` (default),
`this_week`, or `last_week`. Weekly `clients_emailed` ranking returns
`period_unavailable` because the table lacks a per-send timestamp.

Results contain `metric`, `requested_period`, `ranked_campaigns` (up to 20
rows), `leaders`, `highest_count`, tie/truncation flags, a concise `summary`,
and `contact_history_available: false`. Each row includes its selected
`metric_count`, total member count, cumulative emailed-client count, and
members added in the requested period. These are synthetic prototype metrics;
none represents all-channel contact, acquisition, service sales, or proven
email delivery.

### MCP: prepare_campaign_email

The email preview/confirmation implementation below is a legacy contract. Its
storage still depends on `campaign_email_send` and
`mock_campaign_contact_event`, which a fresh setup no longer creates. It must be
migrated separately before this flow can run with only `campaign` and
`campaign_member`; its former event writes do not feed the performance tools.

This tool prepares and persists an email preview; it does not send. Model-facing
arguments are `subject` (1-200 characters), `body` (1-10,000 characters),
optional `campaign_id`, and optional unique `recipient_ids` (1-100). When a
campaign is selected in the UI, trusted request metadata overrides the model's
campaign value. Adviser ID, tenant ID, chat session ID and latest user message
are supplied only through MCP metadata.

The server verifies campaign assignment and active state, recalculates campaign
criteria matches, then loads only adviser-owned contacts. Contacts that are not
matches or lack `opt_in_email` are returned under `excluded_recipients`; they are
never included in the stored batch. Omitting `recipient_ids` selects all matched,
consenting contacts. A successful result contains the exact subject, body,
recipient snapshot, excluded recipients, delivery mode, 15-minute expiry and an
exact `CONFIRM EMAIL <code>` phrase. A newer preview for the same chat session
and campaign supersedes its prior unconfirmed preview.

### MCP: confirm_campaign_email

This consequential tool has no model-facing arguments. The API-side orchestrator
routes an exact confirmation phrase directly, and MCP reads the latest user
message from trusted metadata. General approval language cannot send an email.

The server locks the latest batch, verifies its hashed phrase and expiry, and
rechecks campaign access, criteria matching, ownership and email consent. It
calls the configured transport once for each recipient and stores bounded
per-recipient outcomes. Every successful outcome appends one
`mock_campaign_contact_event` with `engagement_status=0`, `channel=email`, the
delivery mode and `send_batch_id`. Failed or unknown outcomes do not create a
contact event. Repeating a completed confirmation returns the stored result and
does not send again. A deliberate resend requires a new preview and phrase.

Local `EMAIL_DELIVERY_MODE=mock` results are explicitly simulated. Optional
`gwm` mode uses the server-side GWM Core Email API adapter; credentials and
provider settings are never model arguments or browser configuration.

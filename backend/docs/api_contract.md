# PULSE Chat API contract

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
  "ai_answer": "..."
}
```

Provider or MCP tool-server failures are returned as `429`, `502`, `503`, or
`504` depending on the failure category. Groq receives schemas discovered from
the FastMCP server at `MCP_SERVER_URL`; tool calls are executed by that server.
Tool execution is bounded by `LLM_MAX_TOOL_ROUNDS`.
After a successful provider response, the user and assistant messages are stored
in one PostgreSQL transaction. A failed provider request does not append a
partial exchange, although a session explicitly created beforehand remains.

Example:

```bash
curl -X POST http://localhost:4000/chat/query \
  -H 'Content-Type: application/json' \
  -d '{"fa_id":"advisor-123","message_content":"Add 12.5 and 7.5"}'
```

### Error responses

- `400`: neither the body nor query string supplies `fa_id`.
- `404`: the selected session does not exist or belongs to another adviser.
- `422`: request validation failed or the stripped message is empty.
- `429`: the upstream model provider rate-limited the request.
- `502`: provider authentication, response, or tool-loop failure.
- `503`: LLM configuration or PostgreSQL is unavailable.
- `504`: the upstream model request timed out.


## Campaign context and synthetic recommendation tool

`POST /chat/query` and `POST /api/chat/query` additionally accept an optional
`campaign_id` (1-69 letters, digits, hyphens or underscores; starts with a letter or digit). Example:

```json
{
  "fa_id": "adv-steven-raynaldi",
  "campaign_id": "camp-1",
  "message_content": "Which clients are recommended for this campaign?"
}
```

Omitting it preserves existing chat behavior. An invalid ID returns `422`;
an unknown/inaccessible campaign returns `404`; a campaign that is not active
on the fixed demo date returns `409`. Campaign validation happens before session
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
Context is injected by FastMCP and absent from the model-facing schema. It is
read-only and returns synthetic campaign criteria matches, without ranking,
sending outreach or changing CRM data.

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

Model-facing arguments: `campaign` (optional campaign name or ID from the
current user message) and `limit` (integer 1-100, default 5). When the API
request includes a selected `campaign_id`, that server-bound context takes
precedence over the model argument; otherwise the campaign from the current
message is used. The API supplies the adviser identity through
`_meta.pulse_scope`; `fa_id` is not a model argument and is never requested
from the adviser by the assistant. The tool uses that scoped adviser ID when
retrieving unreplied clients.

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

### Campaign generation contracts and ownership

Stages 1-4 define the later draft workflow without enabling campaign creation.
The lifecycle values are `generated`, `reviewed`, `confirmed`, `rejected` and
`expired`. The current retrieval tool stops before `generated`: draft preparation,
revision, preview, confirmation and PostgreSQL persistence remain subsequent
stages.

- Model-generated, adviser-reviewable content: campaign name, description,
  client message, age groups, genders, cash bands, demographic summary,
  field-level rationale, assumptions and disclaimer.
- Adviser-edited content: the same reviewable fields plus later builder metadata
  such as dates, audience source and routing, once those endpoints are built.
- Server-owned content: tenant and adviser ownership, draft and campaign IDs,
  revision and lifecycle state, campaign status, creator, timestamps, hashes,
  signing tokens and idempotency state.

Model-facing contracts reject unknown fields and cannot accept tenant, adviser,
campaign status, creator or creation timestamps. The existing campaign status
constraint already supports `draft`, but stages 1-4 do not write campaigns or
change the current activation behavior. A later confirmation path must force
`status = draft` on the server.


### MCP: get_active_campaigns

This read-only tool shares the existing MCP HTTP endpoint and does not change
recommendation or follow-up tools. No new REST routes, SQL tables, ports or
provisioning steps are required.

The user ID `fa_id` and organisation boundary `tenant_id` come from API request
metadata (`pulse_scope`), never model arguments. Campaigns must have a matching
`mock_campaign_advisor` assignment. Caller-supplied adviser identity remains a
prototype mechanism, not authenticated identity.

Active means status `active` and inclusive start/end dates containing today's
Singapore date. The recommendation tool retains its fixed demo date.

Arguments: optional `campaign_ids` (exact IDs, at most 100), `campaign_names`
(case-insensitive exact names, at most 100), `fields`, and `limit` (strict integer
1–1000, default 1000). Supplying both campaign filters intersects them. An empty
filter list returns no rows. A selected campaign does not narrow general
campaign discovery; use explicit filters for a particular campaign.

Default fields: `campaign_id`, `name`, `start_date`, `end_date`, `age_groups`,
`genders`, `cash_bands`. Other selectable fields: `status`, `age_min`, `age_max`,
`cash_min`, `cash_max`. Campaign name is always included. For general listings,
PULSE is instructed to omit `fields` or pass null to show all default details;
"active" is a filter, not a request for only name and status.

Output: `data_source: synthetic`, `as_of_date`, `columns`, `rows`, a Markdown
`table`, `total_count`, `returned_count`, `truncated`, and a disclaimer.
Structured keys use snake_case; display headers have spaces (Campaign ID,
Start Date, Cash Bands). Empty array criteria display as Any; absent optional
values display as Unknown. Results above the limit are marked truncated;
narrow campaign filters for smaller results.

Missing/inaccessible/inactive campaigns return no rows without disclosing their
existence. Missing scope and database failures return safe structured errors
(`missing_context`, `storage_unavailable`), without connection details or
fabricated fallback records.

Example arguments:

```json
{"campaign_names": ["Legacy Protection Refresh"], "fields": ["name", "end_date"]}
```

Discovery is a synthetic review tool, not a product suitability or consent
check. It does not send communications or mutate CRM records. Client matching
remains available through `recommend_clients_for_campaign`. Consent checks,
authorised outreach, interaction logging, follow-up task creation and outcome
measurement remain separate workflow work.

### MCP: get_campaign_contact_performance

This read-only tool reports recorded outreach for one accessible synthetic
campaign. Model-facing arguments: optional `campaign` (exact name or ID, at most
255 characters) and optional `period` (`this_week`, the default, or `last_week`).
`last_week` means the previous complete Monday–Sunday in Singapore time.
When `/chat/query` or `/api/chat/query` includes a selected
`campaign_id`, that server-bound selection takes precedence. Otherwise the tool
uses the campaign named in the current message. A missing or inaccessible
campaign returns the same `campaign_unavailable` error without revealing another
adviser's relationship. Duplicate accessible names return `campaign_ambiguous`.

The API supplies `fa_id` and `tenant_id` through `_meta.pulse_scope`, not tool
arguments. The tool reads `mock_campaign_contact_event` with both scope fields,
campaign ID, and the inclusive campaign period. It counts distinct clients who
have at least one event from the campaign start through the current Singapore
time or campaign end, whichever comes first. `contacted_clients_this_week`
counts distinct clients with any event since Monday 00:00 Singapore time; repeat
contacts do not double count. `first_contacted_clients_this_week` counts clients
whose earliest event during the campaign period falls this week. A future-dated
event is never counted. `contacted_clients_last_week` and
`first_contacted_clients_last_week` use the preceding Monday 00:00 up to, but
excluding, this Monday 00:00. The campaign-period bounds still apply. No client
details are returned.

Result keys: `data_source: synthetic`, `campaign_id`, `campaign_name`,
`campaign_status`, `reporting_state`, `campaign_start_date`, `campaign_end_date`,
`reporting_period_start`, `reporting_period_end`, `as_of_date`, `as_of_time`,
`requested_period`, `week_start_date`, `last_week_start_date`,
`last_week_end_date`, the five counts, `summary`, and
`metric_definition`. For the supplied sample data, the exact counts vary with
the reporting date. The `summary` is generated from the counts, so the assistant
can answer without estimating.

Missing context or campaign and database outages return structured errors
(`missing_context`, `missing_campaign`, `campaign_unavailable`,
`campaign_ambiguous`, `invalid_campaign_context`, `invalid_arguments`, or
`storage_unavailable`) without counts or raw database details. The existing
`fa_id` in the chat request is caller-supplied; this is a local prototype, not
authenticated adviser identity. No service sales or acquisitions are counted.

### MCP: get_campaign_contact_ranking

This read-only tool compares **distinct clients contacted** across every
synthetic campaign accessible to the requesting adviser and tenant. It answers
questions such as “Which campaign has the highest number of clients?” in the
contact-performance context. It does not rank target audience size, acquisitions,
or sales. A selected campaign in chat does not narrow this comparison.

The only model-facing argument is optional `period`: `campaign_to_date`
(default), `this_week`, or `last_week`. Week boundaries use Singapore time;
`last_week` is the previous complete Monday–Sunday. A contact is counted only
inside its campaign's dates and the requested period, before the reporting time.
Repeat contacts with the same client count once per campaign. Campaigns with no
recorded contacts appear with zero. The database applies adviser and tenant
scope before aggregation and returns no client details.

Result keys: `data_source: synthetic`, `metric: distinct_clients_contacted`,
`requested_period`, `period_start_date`, `period_end_date`, `as_of_time`,
`campaign_count`, `ranking_truncated`, `leaders_truncated`,
`ranked_campaigns` (up to 20 entries with campaign ID, name, status, and count),
`leaders` (all visible campaigns tied for the highest count),
`highest_contacted_clients`, `summary`, and `metric_definition`. More than 20
accessible campaigns sets `ranking_truncated`; if the highest-place tie extends
beyond the returned entries, `leaders_truncated` is also true. No accessible
campaigns produce an empty ranking and a clear summary. Missing adviser context,
invalid arguments, and database outages return structured errors without counts.

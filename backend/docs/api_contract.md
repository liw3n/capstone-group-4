# PULSE Chat API contract

All chat routes are also available with an `/api` prefix.

## `GET /health`

Returns API status, whether an LLM key is configured, and the configured model name.
It never returns the API key.

Example response:

```json
{"status":"ok","llm_configured":true,"llm_model":"openai/gpt-oss-20b"}
```

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

See [campaign_recommendations.md](campaign_recommendations.md) for fake table
assumptions, SQL setup, expected results and commands that work without Groq.

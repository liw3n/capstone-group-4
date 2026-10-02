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

Provider failures are returned as `429`, `502`, `503`, or `504` depending on the
failure category. Tool execution is bounded by `LLM_MAX_TOOL_ROUNDS`.
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

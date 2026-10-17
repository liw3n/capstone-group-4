# MCP Server Guide

## Scope and runtime

`server.py` exposes FastMCP over Streamable HTTP on port `8001` when executed
directly:

```bash
cd backend
uv run python mcp/server.py
```

The endpoint is `/mcp`. The API connects using `MCP_SERVER_URL` and converts
discovered MCP schemas into Groq-compatible function tools. Keep the MCP tool
schemas and API client behavior aligned.

## Change rules

- Define narrow tools with precise type hints, docstrings, bounded inputs, and
  stable structured outputs.
- Treat tool arguments as untrusted. Validate limits and identifiers, use
  parameterized database access, and never return secrets or raw connection
  errors.
- Keep the HTTP transport, port, and endpoint aligned across local startup,
  Docker, Terraform, and API configuration.
- Add unit tests for tool behavior and failure modes before exposing real data.
- Coordinate tool schema changes with the API/client that consumes them and
  with the architecture/API documentation.
- Design product tools around narrow domain operations rather than generic SQL:
  list campaigns, explain eligibility, preview a synthetic audience, draft
  outreach, confirm an action, log an interaction, and create a follow-up task.
- Enforce adviser/tenant scope and communication consent inside tool handlers,
  not through prompt instructions alone.
- Mark read-only versus consequential tools explicitly. Consequential tools
  require a server-verifiable preview/confirmation step and an audit record.

## Known gaps (current state)

- Registered campaign tools use shared handlers for scoped synthetic discovery,
  matching, performance, follow-up, reference retrieval, draft preparation and
  read-only selective draft revision. The generic model-facing tool list still
  hides revision; the chat orchestrator loads the authoritative persisted draft,
  obtains schema-constrained values only for selected fields, and invokes the
  revision tool directly.
- There is no real authentication, production CRM integration, tool-level audit
  log or consent-safe consequential action/confirmation protocol.
- The server starts beside FastAPI in local development and shares its optional
  container; it is not deployed as an independently discoverable service.

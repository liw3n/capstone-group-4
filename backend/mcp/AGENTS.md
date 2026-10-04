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

- Both tools remain demonstrations: database search fabricates results and
  `calculate_sum` is unrelated to the product domain.
- Shared implementations and unit tests now exist, but there is no CRM database
  integration, authentication/authorization, prompt/resource definition,
  tool-level audit logging, or confirmation protocol.
- Nothing starts or deploys this server. Despite the architecture diagram,
  there is no MCP Docker image, ECS task/service, networking, or API-to-MCP
  connection.

# MCP Server Guide

## Scope and runtime

`server.py` is a FastMCP prototype that runs over stdio when executed directly:

```bash
cd backend
uv run python mcp/server.py
```

It exposes the same implementation functions used by the API tool registry.
Keep the MCP schemas and application tool schemas behaviorally aligned even
though their registration mechanisms differ.

## Change rules

- Define narrow tools with precise type hints, docstrings, bounded inputs, and
  stable structured outputs.
- Treat tool arguments as untrusted. Validate limits and identifiers, use
  parameterized database access, and never return secrets or raw connection
  errors.
- Keep transport assumptions explicit. Stdio tools should not print unrelated
  content to stdout.
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

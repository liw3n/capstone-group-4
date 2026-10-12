# Documentation Guide

## Scope

This directory is the source of truth for architecture and API documentation.
Document implemented behavior, and label planned topology or endpoints clearly.

Company-provided objectives/domain/schema references live in repository-level
`docs/` and are inputs, not implementation documentation. Do not copy their
confidential infrastructure identifiers or PDPA examples into this directory.

## Change rules

- Fill in `api_contract.md` whenever endpoint behavior is introduced or
  changed. Include method/path, parameters, body, response, error cases, and a
  minimal example.
- Keep `Architecture.png` synchronized with actual containers, ports, data
  flows, and infrastructure. Prefer committing an editable diagram source in
  addition to the rendered PNG when the diagram is next revised.
- Cross-check docs against `app/main.py`, `Dockerfile`, `setup.sh`, SQL, and
  Terraform rather than copying aspirational behavior as fact.
- When documenting campaign features, cover the complete flow: campaign
  discovery, explainable client matching, consent filtering, outreach preview,
  adviser confirmation, interaction/task logging, and outcome measurement.
- Explicitly label synthetic data, placeholder tools, simulated sends, and
  planned integrations.
- Avoid secrets, personal paths, or environment-specific generated endpoints.

## Known gaps (current state)

- The API contract covers chat, campaign catalogue/state endpoints and current
  campaign tool schemas; consent-safe action endpoints remain unimplemented.
- An editable SVG now accompanies the rendered architecture, but there are no
  architecture decision records or threat/data-flow diagrams.
- FastMCP runs over HTTP on port `8001` beside the API process, and the API
  discovers and executes tools through the MCP protocol. It shares the API
  container rather than running as a separate ECS task.
- The diagram is conceptual: Terraform defines no load balancer, service
  discovery, or stable browser-facing endpoint for the emulated ECS task.

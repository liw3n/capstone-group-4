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

- The API contract documents chat but no campaign/audience/action endpoints or
  tool schemas.
- An editable SVG now accompanies the rendered architecture, but there are no
  architecture decision records or threat/data-flow diagrams.
- FastMCP is shown as a stdio-only development process. There is no deployed
  MCP service or API-to-MCP transport; the API executes shared tools in-process.
- The diagram is conceptual: Terraform defines no load balancer, service
  discovery, or stable browser-facing endpoint for the emulated ECS task.

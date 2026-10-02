# GWM API Specification Guide

## Scope

This directory contains company-provided JSON API specifications. They are
reference contracts, not implementations or permission to call company systems.
Treat endpoints, schemas, authentication details, and examples as confidential.

## Change rules

- Do not reformat or bulk-edit source specifications unless explicitly asked.
- Inspect only the specifications relevant to the task; there are many related
  services and similarly named wrapper/integration APIs.
- Never call a documented company endpoint, authenticate to it, or insert its
  hostname into runtime configuration without explicit user authorisation.
- Implement integrations through a server-side adapter. Never call internal GWM
  services directly from the browser or expose their credentials in Vite.
- Generate clients/types into a clearly generated directory and record the
  source filename/version. Do not hand-edit generated output.
- Enforce timeouts, bounded retries, error translation, adviser/tenant scope,
  and data minimisation at the adapter boundary.
- Redact tokens, account identifiers, and PDPA fields from logs and test
  snapshots. Use synthetic fixtures for contract tests.
- If a specification conflicts with the GCRM table reference or prototype data
  model, document the mapping instead of assuming the identifiers are
  interchangeable.

## Product priorities

For the campaign-companion prototype, first identify contracts needed for
adviser identity, client/contact lookup, consent-aware communication, campaign
data, interaction logging, and follow-up tasks. Portfolio or recommendation APIs
must not be used to produce autonomous financial advice.

## Known gaps

- No server-side GWM adapter, generated client, authentication flow, contract
  tests, or sandbox configuration currently exists.
- The specifications alone do not establish that a safe test environment or
  credentials are available.

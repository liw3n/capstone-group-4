# Company Resource Guide

## Scope and confidentiality

This directory contains company-provided project material. Treat it as
confidential even when a file has no explicit classification label.

- Do not edit, rename, convert, publish, upload, or redistribute these source
  files unless the user explicitly requests it.
- Do not reproduce production hostnames, infrastructure identifiers, personal
  data, or large verbatim excerpts in code, fixtures, logs, issues, prompts,
  screenshots, presentations, or public documentation.
- Use synthetic/mock data only. The capstone explicitly excludes real client or
  financial data.
- When reading PDF or DOCX files, use the appropriate artifact skill and inspect
  complete relevant pages/tables rather than relying only on raw extraction.

## Source hierarchy

- `Pulse Capstone.pdf` defines the project objective, scope, milestones,
  deliverables, and confidentiality terms.
- `FA Domain.docx` defines the Singapore FA context, advisory lifecycle,
  campaign lifecycle, suitability expectations, and educator role.
- `Table Structure_GCRMDB.docx` is a reference catalogue for GCRM entities and
  PDPA/encryption classifications. It is not a complete executable schema.

If the implementation conflicts with these resources, report the conflict and
distinguish current behavior from the intended design. Do not silently rewrite
company source material to match the code.

## Product interpretation

The preferred prototype is a human-supervised campaign companion. The business
flow is:

1. create or receive a campaign;
2. segment and match clients to explicit criteria;
3. execute approved outreach;
4. log interactions and responses;
5. schedule follow-up actions;
6. measure outcomes.

Client matching must be explainable and suitable. Outreach must respect channel
consent and require adviser review. Any generated financial advice requires an
appropriate disclaimer; prefer educational content and workflow assistance.

## Known limitations in the supplied material

- The capstone brief refers to a presentation format in Section 5, but that
  section is absent from the provided copy.
- Detailed columns are missing for key GCRM entities including `campaign`,
  `campaign_member`, `interaction`, and `task_item`.
- The schema catalogue uses inconsistent identifier and timestamp types across
  some tables and does not fully document foreign keys/indexes.
- The schema document includes a production database hostname. Never copy it
  into configuration or attempt to connect to it.

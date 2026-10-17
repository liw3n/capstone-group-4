# Database DDL Guide

## Scope

This directory contains SQL executed by `backend/setup.sh` against the local
PostgreSQL instance. It is a prototype schema, not a verbatim copy of the
company GCRM schema. There is no migration framework. The canonical table
definitions live under `create/`; guarded legacy backfills in the relevant
synthetic seed scripts are tracked in `pulse_schema_migration`.

## Change rules

- Keep setup SQL idempotent because the setup script may run repeatedly.
- Use explicit constraints, foreign keys, indexes, nullability, and timezone
  semantics. Match identifier sizes and types used by the Python models.
- For destructive or incompatible changes, introduce a real versioned migration
  path; do not hide data loss behind `CREATE TABLE IF NOT EXISTS`.
- Test DDL against PostgreSQL, not SQLite, and update storage code and API docs
  in the same change.
- Use `TIMESTAMPTZ` for event timestamps and keep adviser/tenant ownership in
  every campaign, contact, interaction, task, and chat access path.
- Model communication consent explicitly. Audience queries must exclude clients
  who have not opted in to the chosen channel.
- Treat the company GCRM document as a reference, not a complete migration
  specification. Several business tables have descriptions but no columns;
  document any synthetic prototype assumptions rather than claiming parity.
- Mark synthetic seed data clearly and never copy company production hosts,
  identifiers, or real client data into SQL.
- Never place production credentials or data dumps here.

## Known gaps (current state)

- Chat and synthetic campaign records are persisted, but production-compatible
  contact/interaction/task tables do not support the full workflow yet.
- `campaign_generation_clarifications` retains bounded pre-generation answers;
  `campaign_generation_drafts` retains the current validated review-only draft
  and optimistic revision; `campaign_generation_draft_options` retains
  short-lived, revision-bound narrative choices. The chat session holds only the
  active draft pointer. Preview tokens and confirmation state are not yet
  implemented.
- The setup script includes an in-place timestamp conversion rather than a
  versioned migration with rollback and audit history.
- There is no adviser/user foreign key, tenant table, title/summary lifecycle,
  retention policy, encryption-at-rest design, or production-compatible dataset.
- The prototype chat schema intentionally differs from the supplied GCRM chat
  tables; no compatibility mapping or migration plan is documented.

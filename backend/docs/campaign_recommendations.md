# Synthetic campaign recommendation prototype

The adviser opens a seeded campaign, opens PULSE, and clicks **Ask for recommended
clients** (or asks "Which clients are recommended for this campaign?"). The
frontend submits the selected campaign ID; FastAPI verifies access and active
status; the LLM calls the read-only MCP tool; the tool returns criteria matches
and missing information with counts and explanations. There is no ranking.

## Shared setup and frontend demonstration

Use the [team Make workflow](../../README.md#team-setup-and-development-workflow).
From the repository root in the team's macOS/Linux/WSL Bash environment, bootstrap
dependencies, configure the local Groq key, then run:

```bash
make provision
make dev
```

Provisioning runs `backend/setup.sh`. Its ordered SQL loops apply the table
definitions under `backend/tables/create/` before loading the synthetic rows
under `backend/tables/mock_data/`. Every teammate loads the same synthetic
records into their own local database. The campaign and client definitions are
the complete current prototype schema; their seed scripts also contain guarded
compatibility backfills for databases provisioned before schema consolidation.
The scripts are additive and repeatable, and `ON CONFLICT DO NOTHING` preserves
existing edits. Use an explicit versioned migration path for future destructive
or incompatible changes.

`setup.sh` generates `DATABASE_URL` for the provisioned database. The prior
`pulse-postgres:5432` Docker-network address is not the configuration for native
Make-started services. Install the standalone `fakecloud` executable using its
[official installer](https://fakecloud.dev/docs/getting-started/install/) as
described in the shared setup guide. The `localstack` Python dependency does
not provide FakeCloud. With Docker running, `make provision` starts the
emulator automatically and loads the mock tables and data.

`make dev` starts Vite :3000, FastAPI :4000 and MCP :8001 using the shared startup
script. Demonstrate the tool in PULSE at **http://localhost:3000**. No standalone
feature demo program is needed. `matching.py` and `repository.py` are runtime
implementation modules imported by the MCP tool, not separate demo applications.

Expected untouched seed results on the fixed demo date **2026-08-26**:

| Campaign | Evaluated | Matched | Incomplete | Excluded |
| --- | ---: | ---: | ---: | ---: |
| camp-1: Legacy Protection Refresh | 12 | 4 (A, B, C, L) | 2 (J, K) | 6 |
| camp-2: First Home Starter Bundle | 12 | 3 (F, G, H) | 2 (J, K) | 7 |

There are 14 synthetic clients: 12 in the demo adviser's book, one owned by another
adviser and one in another tenant. Out-of-scope clients are never counted or
returned. Every name and identifier is synthetic.

## Automated verification

Run `uv run pytest` from `backend/`. Unit tests inject test-only rows and mock the
provider; runtime recommendations always read PostgreSQL. No Groq key or running
API/MCP processes are needed for those unit tests.

PostgreSQL integration tests are opt-in: set `PULSE_TEST_DATABASE_URL` to a local
test database. They create/drop uniquely named `pulse_campaign_test_*` schemas,
without changing public demo tables. They cover repeatable SQL, ownership, stored
edits, constraints and API-to-MCP-to-PostgreSQL chat with a fake model provider.
The frontend presentation check remains the shared application flow below.

## Mock table assumptions

The company catalogue names campaigns but does not provide campaign columns.
These PostgreSQL tables are a **synthetic prototype**, not production GCRM DDL.

| `mock_campaign` column | Type / meaning |
| --- | --- |
| tenant_id | VARCHAR(64); part of the primary key |
| campaign_id | VARCHAR(69); other primary-key column; camp-1 and camp-2 |
| name | VARCHAR(255); frontend seed campaign name |
| status | VARCHAR(16); draft, active, paused or completed |
| start_date, end_date | DATE; inclusive activity window |
| age_groups | TEXT[]; supported age bands; empty means no band filter |
| genders | TEXT[]; male/female; empty means no gender filter |
| cash_bands | TEXT[]; supported available-cash bands |
| age_min, age_max | Nullable SMALLINT; inclusive custom age range |
| cash_min, cash_max | Nullable NUMERIC(18,2); inclusive custom SGD range |
| created_at | TIMESTAMPTZ; insertion timestamp |

`create/create_mock_campaign.sql` defines the CRM-facing description, client
message, lifecycle/routing metadata, manual audience overrides, lead triage
state, adviser actions, simulated email log and campaign-specific lead records.
`mock_data/mock_campaign.sql` supplies those fields for clean databases and
records its guarded legacy backfills in `pulse_schema_migration`. The checked-in
SQL campaigns are authoritative for the browser instead of being duplicated in
`frontend/src/data/seed.ts`.

`mock_campaign_advisor` has `tenant_id`, `campaign_id`, and `fa_id` as its primary
key. Its composite foreign key points to the campaign in the same tenant. It
models which adviser can access a campaign rather than client membership.

`mock_client` has `tenant_id`, `contact_id` (composite primary key), `fa_id`,
`name`, nullable matching fields (`date_of_birth`, `gender`, `available_cash`),
communication consent, minimal CRM display fields, and a JSONB extension for
synthetic notes/timeline data. Available cash is investable SGD cash, not annual
income. Both consent flags default to false.
Matching returns a review list and does not authorize communications; a future
outreach tool must validate these flags for its chosen channel.

Reads go through `get_campaign(campaign_id, scope)` and
`list_clients_for_fa(scope)` in `app/campaigns/repository.py`. Both use parameterized
SQL with tenant/adviser predicates. Connections are read-only, with five-second
connection and statement timeouts. Database errors become HTTP 503 during campaign
validation or the structured MCP error `storage_unavailable`, without exposing
connection details. There is no global data cache or fallback dataset.

The two checked-in campaigns, and campaigns created in the browser, use
`mock_campaign` as their single campaign-record source. The activity window and
adviser access assignments are prototype assumptions. The frontend CRM and MCP
matching both use the same adviser/tenant-scoped `mock_client` rows, so campaign
recommendation IDs map directly to frontend contact actions.
Product narratives such as protection gaps, review dates or property ownership
are not assessed unless explicit supported criteria are added. Replace this
data-access adapter when the real schema is agreed; matcher and model-facing tool
arguments can remain unchanged.

## Rules and output

- OR within age groups, genders and cash bands; AND across the dimensions.
- A custom numeric range is inclusive and OR'd with its dimension's bands.
- Empty dimensions do not filter.
- Age uses 2026-08-26, matching the frontend demo date, including birthday boundaries.
- Cash bands are [0, 50k), [50k, 250k), [250k, 1m), [1m, infinity).
- A missing/invalid field required by an active filter puts a client in the
  incomplete list. Missing-first behavior matches `targeting.ts`.
- Results use stable contact-ID order, with explanations for each active matched
  dimension. No financial suitability score is invented.
- Default limit is 100, returning all current eligible seeded clients. Both
  lists are bounded; total counts remain uncapped and truncation flags are explicit.
- Evaluated = matched + incomplete + excluded; excluded counts refer only to
  in-scope clients that failed the criteria.

The MCP tool accepts only `campaign_id` and `limit` (integer 1-100).
FastAPI constructs an immutable request scope and the MCP client attaches it via
request metadata. FastMCP injects Context; the LLM never receives an identity
argument. Each orchestration call binds a new registry so concurrent requests
cannot overwrite another adviser's scope. Missing metadata fails closed.

The current API still accepts caller-supplied `fa_id`, fixes the synthetic tenant
to `pulse-demo`, and has no authentication. MCP metadata is trusted only within
this local prototype; direct MCP clients can supply metadata. Before real data,
replace identity derivation with authenticated adviser/tenant claims and secure
the MCP transport. This is not a production security boundary.

## Campaign loop and verification

Matching remains a read-only review list and therefore does not filter by
communication consent. When an adviser separately asks PULSE to prepare email,
the backend turns matching results into a consent-filtered preview and requires
an exact, expiring confirmation phrase before delivery. Successful mock or GWM
adapter results append campaign contact events. Task creation and purchase/outcome
measurement remain unimplemented. The existing frontend send/task flows remain
separate simulations. The tool and system prompt explicitly distinguish criteria
matching from suitability assessment and financial advice.

Manual check with the existing backend/database/provider setup:

1. Complete provisioning, run the checks, and start the shared stack with `make dev`.
2. Sign in as Financial Advisor; open Campaigns > Legacy Protection Refresh.
3. Open PULSE; check the selected campaign name and synthetic-client notice.
4. Click Ask for recommended clients, then send. Expect A/B/C/L, with age/cash
   reasons, two incomplete profiles and the synthetic-data disclaimer.
5. Switch to First Home Starter Bundle and repeat; expect F/G/H.
6. Leave a request in flight and switch campaigns: the panel is remounted and
   aborts the old request so it cannot populate the new campaign's panel.
7. Create a campaign, refresh the browser and sign in with the same role. The
   campaign and its saved UI state should reload from PostgreSQL. PULSE can use
   a newly created active campaign because it reads the same campaign row.
8. Return to the campaign list: no selection is sent; PULSE should ask for a
   campaign when none is named.

Chat history remains adviser/session-based and can contain earlier campaign
answers. The visible selection and system context apply to the next question.
Focused chat rendering tests run with `npm run test:chat` from `frontend/`; there
is no complete frontend component/end-to-end harness. Use the manual flow above
for the interim presentation.

The general system architecture is in `Architecture.svg`, covering CRM state,
chat, AI/MCP, PostgreSQL and the shared development provisioning workflow. The rendered
`Architecture.png` is an older export.

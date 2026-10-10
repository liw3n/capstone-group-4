# Synthetic campaign recommendation prototype

The adviser opens a seeded campaign, opens PULSE, and clicks **Ask for recommended
clients** (or asks "Which clients are recommended for this campaign?"). The
frontend submits the selected campaign ID; FastAPI verifies access and active
status; the LLM calls the read-only MCP tool; the tool returns criteria matches
and missing information with counts and explanations. There is no ranking.

## Local PostgreSQL setup and testing

The recommendation repository reads PostgreSQL, using the same `DATABASE_URL`
as chat storage. There is no automatic fallback to Python data. The mock table
names make the synthetic prototype separate from the unfinished company schema.

With the local `pulse-postgres` container running, run from `backend/`:

```powershell
docker cp .\tables\create_campaign_chat_sessions.sql pulse-postgres:/tmp/chat.sql
docker exec pulse-postgres psql -U postgres -d pulse -v ON_ERROR_STOP=1 -f /tmp/chat.sql
docker cp .\tables\create_mock_campaign_tables.sql pulse-postgres:/tmp/mock-tables.sql
docker exec pulse-postgres psql -U postgres -d pulse -v ON_ERROR_STOP=1 -f /tmp/mock-tables.sql
docker cp .\tables\seed_mock_campaign_data.sql pulse-postgres:/tmp/mock-seed.sql
docker exec pulse-postgres psql -U postgres -d pulse -v ON_ERROR_STOP=1 -f /tmp/mock-seed.sql
```

The schema and seed scripts are additive and repeatable. Seeds use
`ON CONFLICT DO NOTHING`: rerunning them preserves edits to existing demo rows.
They do not reset profiles. No production schema compatibility is claimed.

Copy `.env.example` to the ignored `.env` yourself and configure the database:

- For Python running on Windows: use host `127.0.0.1`, port `55432`, database `pulse`.
- For the API container attached to Docker network `pulse-dev`: use host
  `pulse-postgres`, port `5432`, database `pulse`.
- Set the username/password to those chosen when creating your local database.

To run the full application using Docker, set `DATABASE_URL` in `.env` to
`postgresql://<user>:<password>@pulse-postgres:5432/pulse`, set your actual
`GROQ_API_KEY`, and keep `MCP_SERVER_URL=http://127.0.0.1:8001/mcp`. Then run from
`backend/`:

```powershell
docker build -t pulse-chat-api .
docker run --rm --name pulse-api --network pulse-dev --env-file .env -p 127.0.0.1:4000:4000 pulse-chat-api
```

Keep that terminal running. In another terminal, start Vite from `frontend/`
with `npm run dev`, then open `http://localhost:3000`. The API and MCP run in the
same container; MCP does not need a Windows port mapping. This path uses the
local database container and does not require the FakeCloud setup script.

Install locked dependencies with `uv sync --frozen`. To test recommendations
without a Groq key or running the API/MCP services:

```powershell
uv run python -B -m app.campaigns.demo camp-1
uv run python -B -m app.campaigns.demo camp-2
```

These commands read persisted table rows and print the same structured result as
the MCP tool. A new invocation sees committed database edits. Age calculations
still use the fixed frontend demo date; they do not use the wall clock.

`uv run pytest` tests the matcher, MCP and API without a database or provider key
using test-only repository doubles. PostgreSQL integration tests are opt-in:
set `PULSE_TEST_DATABASE_URL` to a local test database before running pytest.
They create/drop only uniquely named `pulse_campaign_test_*` schemas in that
specified database; they do not change its public tables. Integration checks
cover repeatable SQL, ownership, criteria conversion, stored edits, constraints
and the complete API-to-MCP-to-PostgreSQL chat path with a fake AI provider.

Expected demo results as of **2026-08-26**:

| Campaign | Evaluated | Matched | Incomplete | Excluded |
| --- | ---: | ---: | ---: | ---: |
| camp-1: Legacy Protection Refresh | 12 | 4 (A, B, C, L) | 2 (J, K) | 6 |
| camp-2: First Home Starter Bundle | 12 | 3 (F, G, H) | 2 (J, K) | 7 |

There are 14 seeded synthetic clients: 12 in the demo adviser's book, one owned by another
adviser and one in another tenant. Out-of-scope clients are never counted or
returned. Every name and identifier in these seed rows is synthetic.

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

`mock_campaign_advisor` has `tenant_id`, `campaign_id`, and `fa_id` as its primary
key. Its composite foreign key points to the campaign in the same tenant. It
models which adviser can access a campaign rather than client membership.

`mock_client` has `tenant_id`, `contact_id` (composite primary key), `fa_id`,
`name`, nullable `date_of_birth`, nullable `gender`, nullable `available_cash`
(NUMERIC(18,2)), `opt_in_email`, `opt_in_sms`, and `created_at`. Available cash is
investable SGD cash, not annual income. Both consent flags default to false.
Matching returns a review list and does not authorize communications; a future
outreach tool must validate these flags for its chosen channel.

Reads go through `get_campaign(campaign_id, scope)` and
`list_clients_for_fa(scope)` in `app/campaigns/repository.py`. Both use parameterized
SQL with tenant/adviser predicates. Connections are read-only, with five-second
connection and statement timeouts. Database errors become HTTP 503 during campaign
validation or the structured MCP error `storage_unavailable`, without exposing
connection details. There is no global data cache or fallback dataset.

Both campaigns mirror the frontend seeds. The activity window and adviser access
assignments are prototype assumptions. The backend's separate 14-client dataset
is **not** the frontend's 75 contact records, and recommendation IDs cannot be
used for existing frontend email/task actions. Browser-created campaigns remain
local React state and are not inserted into these tables. Product narratives such
as protection gaps, review dates or property ownership are not assessed unless
explicit supported criteria are added. Replace this data-access adapter when the
real schema is agreed; matcher and model-facing tool arguments can remain unchanged.

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

This change implements selection, explainable matching and a read-only conversation.
It does not authorise outreach. Matching does not filter by communication consent
because it produces a review list, not recipients. Consent validation, outreach
preview/confirmation, interaction/task logging and outcome measurement still need
backend implementations. The existing frontend send/task flows remain separate
simulations. The tool and system prompt explicitly distinguish criteria matching
from suitability assessment and financial advice.

Manual check with the existing backend/database/provider setup:

1. Run frontend TypeScript checking and build; start the frontend and backend.
2. Sign in as Financial Advisor; open Campaigns > Legacy Protection Refresh.
3. Open PULSE; check the selected campaign name and synthetic-client notice.
4. Click Ask for recommended clients, then send. Expect A/B/C/L, with age/cash
   reasons, two incomplete profiles and the synthetic-data disclaimer.
5. Switch to First Home Starter Bundle and repeat; expect F/G/H.
6. Leave a request in flight and switch campaigns: the panel is remounted and
   aborts the old request so it cannot populate the new campaign's panel.
7. Return to the campaign list: no selection is sent; PULSE should ask for a
   campaign when none is named. A browser-created campaign should show the
   unavailable-campaign error instead of invented matches.

Chat history remains adviser/session-based and can contain earlier campaign
answers. The visible selection and system context apply to the next question.
There is no frontend automated test harness; use the manual flow above.

The general system architecture is in `Architecture.svg`, covering CRM state,
chat, AI/MCP, PostgreSQL and optional development infrastructure. The rendered
`Architecture.png` is an older export.

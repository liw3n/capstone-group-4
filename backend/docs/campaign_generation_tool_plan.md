# Campaign generation MCP tool implementation plan

This plan adds an adviser-facing workflow that converts a plain-language business
objective into a structured campaign draft. The first release will use the
existing chat orchestrator to generate schema-constrained MCP tool arguments. The
MCP tool will validate and return a draft without creating a campaign. The
adviser can then review and edit every field before a separate, explicit
confirmation creates the campaign with `draft` status.

The feature is complete when the five reference cases in
`campaign_generation_test_cases.md` produce valid, reviewable drafts; generation
and regeneration cannot mutate campaign records; and only the latest
adviser-confirmed draft revision can be created.

## Product behavior

The supported flow is:

1. The adviser enters a business objective in PULSE or the campaign builder.
2. The system retrieves up to three relevant, approved entries from a curated
   campaign catalogue.
3. The model uses the objective, schema and retrieved references to propose a
   campaign name, description, client message and targeting criteria.
4. The MCP tool validates and normalises the proposal.
5. The frontend displays the structured fields, assumptions, source references
   and targeting rationale in an editable review form.
6. The adviser edits fields or regenerates selected sections.
7. The frontend shows a final preview.
8. The adviser explicitly confirms creation.
9. The server creates one campaign with `status = "draft"`.
10. Campaign activation remains a separate action outside generation.

Generation must not select actual clients, perform a suitability assessment,
activate a campaign, send communications or write campaign records.

## Architecture decision

The initial implementation will use one model interaction through the existing
`ChatOrchestrator`. The model will construct the complete arguments for a new
`prepare_campaign_draft` MCP tool. The tool will provide the trusted boundary for
schema and policy validation and return a structured artifact.

This avoids a second model call inside MCP, reduces latency and fits the current
OpenAI-compatible tool loop. The name `prepare_campaign_draft` is deliberate: the
model produces the language, while the tool validates and packages it. If the
tool later needs to work independently for non-PULSE MCP clients, generation can
be moved behind a shared campaign-draft service without changing the output
contract.

The resulting flow is:

```text
User objective
    -> FastAPI chat query
    -> ChatOrchestrator
    -> find_campaign_references MCP tool
    -> approved catalogue entries with provenance
    -> LLM generates prepare_campaign_draft arguments
    -> FastMCP validates and returns a campaign_draft artifact
    -> ChatOrchestrator retains the structured artifact
    -> FastAPI returns assistant text plus campaignDraft JSON
    -> CampaignBuilder opens an editable review
```

## Scope

### Included

- Generate the six requested campaign fields from a natural-language objective.
- Retrieve a bounded set of approved, relevant campaign references.
- Return catalogue provenance with the generated draft.
- Validate exact age, gender and cash-band enum values.
- Return assumptions and field-level targeting rationale.
- Regenerate selected fields while preserving all other fields.
- Return structured JSON to the frontend rather than requiring prose parsing.
- Require an explicit, server-verified confirmation before creation.
- Create approved campaigns with `draft` status.
- Record enough generation metadata for prototype auditability.
- Add deterministic tests and model-quality evaluation cases.

### Excluded

- Autonomous campaign activation or publication.
- Client matching, suitability assessment or product recommendation.
- Automatic outreach or consent determination.
- Generation of product rates, premiums, returns or regulatory claims.
- Production authentication, authorisation or a production GCRM integration.
- Treating model-generated confidence scores as evidence of correctness.

## Data contracts

### Generated campaign draft

Create shared Pydantic models outside `main.py` so FastAPI routes, the MCP server
and tests use one contract.

```python
class CampaignDraftCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ageGroups: list[Literal[
        "under35", "35to44", "45to54", "55to64", "65plus"
    ]]
    genders: list[Literal["male", "female"]]
    cashBands: list[Literal[
        "under50k", "50kTo250k", "250kTo1m", "above1m"
    ]]


class CampaignDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10_000)
    clientMessage: str = Field(min_length=1, max_length=10_000)
    criteria: CampaignDraftCriteria
    targetDemographicSummary: str = Field(min_length=1, max_length=1_000)
    rationale: dict[Literal["ageGroups", "genders", "cashBands"], str]
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    disclaimer: str = Field(min_length=1, max_length=1_000)
```

`targetDemographicSummary`, `rationale`, `assumptions` and `disclaimer` are review
metadata in the first release. They are not copied into `mock_campaign` unless a
separate data-model decision explicitly adds fields for them.

### Curated campaign catalogue entry

Start with a small, versioned catalogue rather than a vector database. Each
entry must be synthetic, reviewed and explicitly approved for reuse.

```python
class CampaignReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referenceId: str
    title: str
    category: Literal[
        "retirement", "protection", "education", "legacy", "property", "other"
    ]
    objectiveTags: list[str]
    descriptionPattern: str
    messagingPattern: str
    typicalCriteria: CampaignDraftCriteria
    targetingRationale: dict[str, str]
    requiredDisclaimers: list[str]
    prohibitedClaims: list[str]
    approvalStatus: Literal["approved", "retired"]
    version: int = Field(ge=1)
    validFrom: date
    validUntil: date | None = None
```

The runtime catalogue must not contain actual client lists, account identifiers,
personal data, production infrastructure details or unapproved model output.
Adviser approval of an individual campaign does not automatically approve it as
a reusable catalogue entry.

### Retrieval tool arguments and result

```python
class CampaignReferenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=10, max_length=2_000)
    categories: list[str] | None = Field(default=None, max_length=5)
    limit: int = Field(default=3, ge=1, le=3, strict=True)
```

```json
{
  "type": "campaign_references",
  "query": "...",
  "retrievalToken": "opaque-server-verifiable-token",
  "references": [
    {
      "referenceId": "campaign-pattern-retirement-001",
      "version": 1,
      "category": "retirement",
      "matchedTags": ["retirement-readiness", "asset-consolidation"],
      "descriptionPattern": "...",
      "messagingPattern": "...",
      "typicalCriteria": {},
      "targetingRationale": {},
      "requiredDisclaimers": []
    }
  ],
  "truncated": false
}
```

Only the minimum fields needed for generation should be returned. Retrieval must
exclude retired, expired, cross-tenant or otherwise unauthorised entries before
ranking them.

### Prepare tool arguments

```python
class PrepareCampaignDraftArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=10, max_length=2_000)
    retrievalToken: str
    referencesUsed: list[CampaignReferenceCitation] = Field(max_length=3)
    draft: CampaignDraft
```

`CampaignReferenceCitation` contains only `referenceId` and `version`. The
opaque retrieval token binds the objective hash, adviser and tenant scope,
retrieved reference IDs and versions, catalogue version and a short expiry. The
draft handler verifies the token and requires `referencesUsed` to be a subset of
the references actually returned. An empty retrieval result still returns a
valid token with an empty allowed-reference set.

### Tool result

```json
{
  "type": "campaign_draft",
  "data_source": "ai_generated",
  "objective": "...",
  "referencesUsed": [
    {"referenceId": "campaign-pattern-retirement-001", "version": 1}
  ],
  "draft": {},
  "validation": {
    "schema_valid": true,
    "policy_valid": true,
    "warnings": []
  },
  "requires_adviser_review": true,
  "created": false
}
```

The tool must return stable error codes such as `invalid_draft`,
`unsupported_claim`, `missing_disclaimer`, `inconsistent_targeting` and
`missing_context`. It must not return provider errors, database details or
secrets.

### Chat response

Replace the string-only internal result with a typed envelope:

```python
class OrchestratorResult:
    answer: str
    artifacts: list[dict[str, Any]]
```

Extend the HTTP response without removing existing fields:

```python
class QueryResponse(BaseModel):
    user: bool | str
    timestamp: str
    ai_answer: str
    campaignDraft: CampaignDraftArtifact | None = None
```

Existing clients that only read `ai_answer` must continue to work.

## Trust and validation controls

Schema validation establishes structural correctness only. The server must also
apply deterministic policy validation before returning a usable artifact.

Reject a draft when it contains:

- unknown fields or unsupported enum values;
- empty required content or content above configured limits;
- invented rates, premiums, returns, guarantees or claims of regulatory
  approval;
- instructions to send, activate or create a campaign automatically;
- client names, account identifiers or other personal data;
- targeting rationale that contradicts the structured criteria;
- client messaging without the required educational and suitability disclaimer.

Return a warning or clarification request when:

- the objective uses undefined terms such as "high-value" without a threshold;
- the objective does not support a defensible age, gender or cash criterion;
- the model applies a demographic restriction not stated or justified by the
  objective;
- the draft depends on a material assumption.

Do not return a numeric model-confidence score. Return concrete validation
results, assumptions and unanswered questions.

Catalogue content is untrusted reference input. Schema validation, policy checks
and adviser review remain mandatory even when every retrieved entry is approved.
The generated draft must identify the exact reference IDs and versions used so
the reviewer can distinguish sourced patterns from model-created wording.

## Curated catalogue governance

Begin with approximately 10 to 20 synthetic entries covering the supported
campaign categories. Use a checked-in JSON or YAML catalogue for the first
release so changes are reviewable in Git and retrieval remains deterministic.
Move to PostgreSQL only when non-developer catalogue management or tenant-specific
entries become necessary.

Every catalogue change must:

- use a stable reference ID and monotonically increasing version;
- identify its category and objective tags;
- contain schema-compatible targeting criteria and rationale;
- include required disclaimers and prohibited claims;
- be reviewed before `approvalStatus` becomes `approved`;
- define validity dates and support retirement without deleting audit history;
- remain synthetic and free of personal data;
- receive regression tests for parsing, filtering and retrieval.

Never add generated campaigns automatically. Promotion into the catalogue must
be a separate, authorised curation workflow. The catalogue is guidance, not a
source of client eligibility or evidence that a campaign is suitable.

Keep catalogue fixtures separate from model-quality holdout cases. Some campaign
patterns may resemble the five documented test cases, but an evaluation case
must not retrieve its expected answer verbatim.

## Retrieval pipeline

The first release should use transparent metadata and lexical scoring rather
than embeddings:

1. Validate and normalise the objective without removing financially meaningful
   terms.
2. Filter to `approvalStatus = "approved"` and a validity window containing the
   current date.
3. Enforce tenant and confidentiality scope before any ranking.
4. Match explicit categories when the user supplies them.
5. Score objective tags, category terms and bounded full-text overlap.
6. Apply a stable tie-break using reference ID and version.
7. Return at most three references and only the fields required for generation.
8. Issue a short-lived, server-verifiable retrieval token bound to the objective,
   request scope, catalogue version and returned reference IDs and versions.
9. Record reference IDs, versions and match reasons in the draft artifact.
10. If nothing passes the minimum relevance rule, return no references and allow
   generation from the schema, while clearly reporting that no catalogue entry
   was used.

The model must not choose its own unseen catalogue records or claim that it used
a reference absent from the retrieval result. The `prepare_campaign_draft`
handler must reject an invalid or expired retrieval token and any unknown, stale
or non-retrieved reference citation.

If the catalogue later becomes too large for metadata and lexical search, add a
semantic-retrieval stage after authorisation filtering. Vector similarity must
not bypass approval, validity, tenant or confidentiality filters. Preserve the
same bounded result and provenance contract so generation code does not depend
on the retrieval implementation.

## MCP implementation

1. Add shared draft models and policy validation under
   `backend/app/campaigns/`.
2. Add a versioned synthetic campaign catalogue and deterministic repository.
3. Add a shared `execute_find_campaign_references` handler under
   `backend/app/tools/`.
4. Register `find_campaign_references` in `backend/mcp/server.py` with
   `readOnlyHint = true` and `destructiveHint = false`.
5. Add a shared `execute_prepare_campaign_draft` handler under
   `backend/app/tools/`.
6. Register `prepare_campaign_draft` in `backend/mcp/server.py` with
   `readOnlyHint = true` and `destructiveHint = false`.
7. Read adviser and tenant scope only from MCP request metadata.
8. Add explicit argument validation in `MCPToolRegistry` before invoking the MCP
   server.
9. Return a structured artifact with `created = false` on every successful call.
10. Add system-prompt guidance requiring reference retrieval before draft
    preparation and prohibiting campaign creation in the same turn.
11. Bound objective length, retrieval count, draft size, execution time and
    tool-call rounds.

Neither tool may query client records. The checked-in five reference cases should
primarily remain evaluation fixtures rather than all being injected into every
prompt.

## Structured artifact handling

The current orchestrator sends tool output back to the model and then discards
its structure when it returns the final assistant string. Update it to retain
recognised artifacts separately from ordinary tool results.

Only results with the expected `type`, schema and tool name may become a
`campaignDraft` response. Treat all MCP output as untrusted and validate it again
at the API boundary. The model's final prose must not overwrite the structured
artifact.

If multiple campaign drafts are returned in one turn, reject the ambiguous result
or return only the final validated revision according to an explicit rule. The
initial implementation should allow at most one campaign-draft artifact per
request.

## Regeneration design

Add a separate `revise_campaign_draft` operation with:

- the current validated draft;
- the exact fields to regenerate;
- an optional adviser instruction;
- the current draft revision.

Allowed fields are `name`, `description`, `clientMessage`, `ageGroups`,
`genders`, `cashBands` and `targetDemographicSummary`.

After generation, server code must restore every field not listed for
regeneration from the original draft. Do not rely on the model to preserve them.
Run the complete schema and policy validation again. Increment the revision and
invalidate any earlier confirmation token.

## Review and confirmation workflow

The frontend should display:

- the original objective;
- every generated campaign field in an editable control;
- field-level targeting rationale;
- assumptions and clarification warnings;
- validation status;
- buttons to regenerate individual sections;
- a final preview and explicit confirmation control.

Persist generated drafts separately from campaigns. After the orchestrator
returns a validated artifact, the API stores a `campaign_generation_draft` row
and returns its `draftId` and `revision`. Generation may create or update this
draft record, but neither generation nor regeneration may write to
`mock_campaign` or `mock_campaign_advisor`.

Manual edits and section regeneration update the draft row using optimistic
locking. The request supplies the last observed revision; the server rejects a
stale revision and increments the revision after every successful update.

Immediately before confirmation, the frontend requests a final preview. The
server reloads the adviser-owned draft, reruns schema and policy validation,
computes a canonical content hash and returns a short-lived confirmation token
bound to:

- draft identifier and revision;
- canonical content hash;
- adviser and tenant scope;
- validation result;
- token expiry.

Any edit or regeneration increments the revision and invalidates the earlier
token. The confirmation request contains the draft ID, revision and token, not a
second untrusted copy of the campaign fields.

Use these route forms while both API prefixes are supported:

- `POST /campaign-drafts/{draft_id}/preview` and
  `POST /api/campaign-drafts/{draft_id}/preview`;
- `POST /campaign-drafts/{draft_id}/confirm` and
  `POST /api/campaign-drafts/{draft_id}/confirm`.

Confirmation is an ordinary FastAPI operation rather than an MCP tool. Do not
expose an unrestricted create-campaign tool to the model or let the model mint a
confirmation token.

### Database write after confirmation

When the adviser clicks Confirm, the server performs the following work in one
PostgreSQL transaction:

1. Resolve the authenticated adviser and tenant scope. The current request-supplied
   adviser ID remains a prototype limitation and must not be treated as production
   authentication.
2. Lock the matching `campaign_generation_draft` row with `SELECT ... FOR UPDATE`
   and enforce adviser and tenant ownership in the query.
3. If the draft is already confirmed with the same idempotency key, return the
   previously created campaign. Reject conflicting repeated confirmation.
4. Verify the draft is confirmable, the supplied revision is current, the token
   is valid and unexpired, and the stored content hash matches the token.
5. Revalidate the stored JSON against `CampaignDraft` and all deterministic policy
   checks. Never trust validation results stored by an earlier process alone.
6. Generate the campaign ID on the server. Copy only approved campaign fields
   from the reviewed draft. Derive ownership, tenant, origin, creator and creation
   timestamp from server context.
7. Force `status = "draft"` regardless of model or browser input. Validate the
   reviewed start date, end date, audience source and routing fields supplied
   through the campaign-builder review step.
8. Insert the `mock_campaign` row using parameterised SQL.
9. Insert the corresponding `mock_campaign_advisor` ownership or assignment rows
   in the same transaction.
10. Update `campaign_generation_draft` to `confirmed`, record the created campaign
    ID, confirmed revision, confirmation time and idempotency key.
11. Commit and return the newly created `CampaignPayload`. If any step fails,
    roll back all three writes so no partial campaign or assignment remains.

The current catalogue service opens its own connection. Refactor it to accept a
caller-owned transaction, or add a dedicated `confirm_campaign_draft` repository
function that owns the complete transaction. Do not call the current
connection-owning `create_campaign` function and then update the draft in a
separate transaction.

The existing `mock_campaign.status` constraint already permits `draft`. The
confirmation path must supply `draft` explicitly because the current API and
catalogue creation defaults are `active`; align those defaults separately so an
omitted browser field cannot activate a campaign.

Campaign activation remains a separate, explicitly confirmed lifecycle action
and is not part of this generation workflow.

## Frontend integration

1. Extend `chatApi.ts` with the optional structured draft response.
2. Add an action in `ChatPanel` to open the generated artifact in
   `CampaignBuilder`.
3. Allow `CampaignBuilder` to accept initial generated values without
   immediately saving them.
4. Clearly label every generated field and assumption.
5. Preserve manual adviser edits when unrelated sections are regenerated.
6. Display policy errors as actionable corrections rather than silently fixing
   material targeting decisions.
7. Require the existing review UI plus a final confirmation before submitting
   the creation request.

The frontend must not parse campaign fields from `ai_answer` and must not receive
database credentials or provider keys.

## Persistence and auditability

Introduce a versioned PostgreSQL migration and a tenant-scoped
`campaign_generation_draft` table rather than a module-global cache. The table
should record:

- `draft_id`, `tenant_id` and `fa_id`;
- original objective;
- structured draft JSON;
- reviewed creation metadata such as dates, audience source and routing;
- retrieved reference IDs and versions;
- revision and status (`generated`, `reviewed`, `confirmed`, `rejected` or
  `expired`);
- canonical content hash;
- validation results;
- model and prompt versions;
- creation and update timestamps;
- confirmation timestamp and confirmed revision;
- confirmation-token expiry metadata without storing a reusable plaintext token;
- idempotency key and created campaign ID.

Add constraints and indexes for adviser and tenant lookup, current status and
created campaign ID. Enforce one created campaign per draft with a uniqueness
constraint. If `created_campaign_id` is represented as a foreign key, use the
same `(tenant_id, campaign_id)` types as `mock_campaign`.

Store only synthetic prototype data. Apply retention rules before any production
use. Every read and mutation must enforce both adviser and tenant ownership.

## Testing and evaluation

### Unit tests

- Parse and validate every curated catalogue entry.
- Exclude unapproved, retired, expired and cross-tenant catalogue entries.
- Return a stable maximum of three references with deterministic tie-breaking.
- Return an empty, non-error result when no reference is relevant.
- Accept every valid enum combination and reject unsupported values.
- Reject unknown fields, missing fields and oversized input.
- Reject prohibited or unsupported claims.
- Require disclaimers and adviser-review metadata.
- Verify MCP generation handlers perform no database writes and API draft
  persistence never writes campaign tables.
- Verify unrequested fields remain byte-for-byte equivalent during regeneration.
- Verify stable, safe error codes and messages.

### Orchestrator tests

- A campaign-generation request calls `find_campaign_references` before
  `prepare_campaign_draft`.
- Only returned reference IDs may appear in the generated artifact.
- An empty retrieval result still permits a schema-grounded draft.
- A campaign-generation request calls `prepare_campaign_draft`.
- Ordinary campaign discovery and recommendation requests retain current tool
  behavior.
- The structured tool artifact is retained independently of assistant prose.
- Invalid or malicious MCP output cannot become an API artifact.
- No more than one campaign draft is accepted per turn.
- Tool-loop and provider failures preserve the existing mapped error behavior.

### API tests

- `/api/chat/query` remains backward compatible and returns `campaignDraft` when
  generation succeeds.
- The draft artifact reports the exact reference IDs and versions used.
- Adviser and tenant scope cannot be supplied by model tool arguments.
- Generation and regeneration leave `mock_campaign` unchanged.
- Stale, expired or cross-adviser confirmation is rejected.
- Valid confirmation creates exactly one `draft` campaign.
- Confirmation atomically creates the campaign and adviser assignment and marks
  the source draft confirmed.
- A failure after any attempted insert rolls back the campaign, assignment and
  draft-status change.
- Repeated confirmation with the same idempotency key returns the same campaign;
  a conflicting repeat returns a deliberate conflict.
- Browser or model attempts to confirm `active` are ignored or rejected; the
  stored campaign is always `draft`.

### Frontend tests

Introduce a frontend test runner before relying on component-level automation.
Cover draft population, field editing, section regeneration, validation errors,
stale responses and final confirmation. Until then, run strict TypeScript checks
and the production build and document the missing automated UI coverage.

### Model-quality evaluations

Use the five cases in `campaign_generation_test_cases.md` as initial golden
scenarios. Evaluate semantic properties rather than exact wording:

- all required fields are present;
- criteria are valid and defensibly follow from the objective;
- assumptions are visible;
- targeting summaries and rationales agree with enum values;
- client messaging is educational and avoids guarantees;
- disclaimers are appropriate;
- no campaign-table mutation occurs before explicit confirmation.

Maintain separate development, catalogue and holdout sets. An example used as a
retrievable catalogue entry must not be scored as an unseen holdout case. Add
retrieval metrics for relevance, approval filtering, provenance accuracy and the
frequency with which generation succeeds safely when no reference is found.

Expand the evaluation set with ambiguous, conflicting and adversarial objectives,
including prompt injection, undefined "high-value" segments, unsupported product
claims, unjustified demographic targeting and requests to bypass review. Critical
policy or mutation violations have zero tolerance. Keep live-model evaluations
separate from deterministic unit tests so provider variability does not make the
normal test suite flaky.

## Delivery stages

Complete each stage and its exit criteria before beginning a dependent stage.

Implementation status as of 12 October 2026: Stages 1-4 are implemented and
covered by deterministic backend tests. They add shared contracts, a versioned
12-entry synthetic catalogue, scoped deterministic retrieval, signed retrieval
tokens and the read-only `find_campaign_references` MCP tool. They do not yet
generate or persist a campaign draft; that begins in Stage 5.

### Stage 1 Define shared contracts and lifecycle boundaries

Implementation:

- Move reusable campaign criteria definitions into a shared model module.
- Add catalogue, retrieval, draft, revision, preview and confirmation models.
- Define stable error codes and the generated-to-confirmed draft lifecycle.
- Document which fields are model-generated, adviser-edited and server-owned.
- Align the proposed `draft` creation behavior with the existing campaign status
  constraint without changing activation behavior yet.

Exit criteria:

- All contracts reject unknown fields and unsupported enum values.
- No model-facing contract accepts tenant, adviser, campaign status, creator or
  creation timestamp.

### Stage 2 Seed the curated knowledge base

Implementation:

- Create a checked-in, versioned catalogue file with 10 to 20 synthetic entries.
- Cover retirement, protection, education, legacy, property and general planning
  objectives.
- Add objective tags, reusable description and messaging patterns, typical
  criteria, rationale, disclaimers, prohibited claims, approval state and validity
  dates.
- Use selected development examples as inspiration, but keep holdout evaluation
  cases outside the runtime catalogue.
- Add a catalogue loader that fails fast on duplicate IDs, invalid versions,
  invalid dates or schema violations.

Exit criteria:

- Every catalogue entry is synthetic, schema-valid and explicitly approved.
- Catalogue parsing and duplicate/version checks are deterministic and tested.

### Stage 3 Implement the catalogue retrieval service

Implementation:

- Implement authorisation, approval and validity filtering before scoring.
- Add category, objective-tag and bounded lexical-overlap scoring.
- Add a stable reference-ID/version tie-break and a maximum result count of three.
- Generate the opaque retrieval token containing the objective hash, scope,
  catalogue version, allowed references and expiry.
- Return an empty successful result when nothing meets the relevance threshold.

Exit criteria:

- The same input and catalogue version produce the same ordered results.
- Retired, expired, unapproved and unauthorised references cannot be returned.
- Token verification rejects altered, expired or cross-scope retrieval contexts.

### Stage 4 Implement the find campaign references MCP tool

Implementation:

- Add `execute_find_campaign_references` as a shared handler.
- Register `find_campaign_references` in FastMCP as read-only and
  non-destructive.
- Validate arguments in both `MCPToolRegistry` and the MCP server.
- Pass adviser and tenant scope through trusted MCP metadata only.
- Return bounded reference fields, match reasons, versions and retrieval token.

Exit criteria:

- Direct MCP tests cover matches, no matches, truncation and safe failures.
- The tool cannot access client records or mutate any database table.

### Stage 5 Implement the prepare campaign draft MCP tool

Implementation:

- Add deterministic policy validation and `execute_prepare_campaign_draft`.
- Register `prepare_campaign_draft` as read-only and non-destructive.
- Require a valid retrieval token and permit only retrieved reference citations.
- Validate the generated fields, rationale, assumptions and disclaimer.
- Return exactly one typed `campaign_draft` artifact with `created = false`.
- Update the system prompt so campaign-generation requests retrieve references
  first and then call this tool.

Exit criteria:

- Invalid, unsafe or incorrectly cited drafts return stable safe errors.
- Successful calls return structured drafts and never write campaign or draft
  tables.

### Stage 6 Implement the revise campaign draft MCP tool

Implementation:

- Register `revise_campaign_draft` as read-only and non-destructive.
- Accept the validated current draft, current revision, selected fields and
  adviser instruction.
- Restore every unselected field in server code after generation.
- Rerun complete schema, citation and policy validation.
- Return the revised artifact; let the API persist the next revision.

Exit criteria:

- Unselected fields remain exactly unchanged.
- Any revision invalidates the prior preview token.
- Revision tool calls do not write campaign tables.

### Stage 7 Retain structured artifacts and persist draft revisions

Implementation:

- Change the orchestrator to return assistant text plus typed artifacts.
- Validate MCP artifacts again at the API boundary.
- Create the `campaign_generation_draft` migration, constraints and indexes.
- Store generated artifacts and provenance after successful orchestration.
- Add scoped read and optimistic-lock update functions for manual edits and
  revised artifacts.
- Extend both `/chat/...` and `/api/chat/...` response forms without breaking
  existing consumers.

Exit criteria:

- Chat returns a `draftId`, revision and structured draft without prose parsing.
- Generation and revision write only the draft table and never campaign tables.
- Stale draft updates and cross-adviser access are rejected.

### Stage 8 Implement the frontend review and regeneration experience

Implementation:

- Add an action in `ChatPanel` to open the draft in `CampaignBuilder`.
- Populate editable fields from the structured artifact.
- Display assumptions, rationale, validation warnings and catalogue provenance.
- Save manual edits with revision checks.
- Connect per-section regeneration to `revise_campaign_draft`.
- Add a final preview step; do not show Confirm until the server validates the
  latest revision.

Exit criteria:

- The adviser can edit or regenerate every generated field.
- Stale responses cannot overwrite newer edits.
- No review action creates or activates a campaign.

### Stage 9 Implement preview and confirmation endpoints

Implementation:

- Add paired `/campaign-drafts/...` and `/api/campaign-drafts/...` preview and
  confirmation routes.
- Issue preview tokens bound to the latest canonical content hash and revision.
- Add idempotency keys and deliberate stale, expired and cross-scope errors.
- Keep confirmation out of MCP and require an explicit frontend click.

Exit criteria:

- Only a currently valid preview can be confirmed.
- Editing or regenerating after preview makes confirmation fail until a new
  preview is issued.

### Stage 10 Implement the atomic PostgreSQL campaign write

Implementation:

- Add a transaction-aware `confirm_campaign_draft` repository operation.
- Lock and revalidate the draft, derive trusted ownership fields and generate the
  campaign ID.
- Force campaign status to `draft`.
- Insert `mock_campaign` and `mock_campaign_advisor`, then mark the generation
  draft confirmed in the same transaction.
- Return the stored campaign and support safe idempotent retries.
- Add rollback tests that fail after each write boundary.

Exit criteria:

- One confirmation creates exactly one campaign and the correct ownership rows.
- Partial writes are impossible under tested failure conditions.
- Repeated requests cannot create duplicates.
- The resulting campaign is `draft`; activation requires a separate action.

### Stage 11 Complete evaluation and documentation

Implementation:

- Run the five golden scenarios and an expanded ambiguous and adversarial set.
- Measure retrieval relevance, provenance accuracy and safe no-match behavior.
- Document failure modes, accepted limitations and catalogue governance.
- Update `api_contract.md`, backend README and architecture diagram.
- Run the full repository verification suite.

Exit criteria:

- Critical policy, ownership, mutation and confirmation tests have zero failures.
- Interfaces, ports, persistence and data ownership are accurately documented.

## Expected file changes

- `backend/app/campaigns/models.py` or `drafts.py`: shared draft contracts.
- `backend/app/campaigns/validation.py`: deterministic policy checks.
- `backend/app/campaigns/catalogue.json`: versioned synthetic approved patterns.
- `backend/app/campaigns/reference_repository.py`: filtering and deterministic
  retrieval.
- `backend/app/campaigns/draft_repository.py`: scoped draft revisions, preview
  state and atomic confirmation.
- `backend/app/tools/campaign_references.py`: retrieval MCP handler.
- `backend/app/tools/campaign_draft.py`: prepare and revise MCP handlers.
- `backend/mcp/server.py`: tool registration.
- `backend/app/tools/mcp_registry.py`: client-side argument validation.
- `backend/app/llm/orchestrator.py`: generation instructions and artifact capture.
- `backend/app/main.py`: response model and confirmation route integration.
- `backend/app/campaigns/catalog.py`: confirmed creation through the existing
  storage boundary.
- `backend/tables/create_campaign_generation_drafts.sql`: draft, revision,
  provenance, confirmation and created-campaign linkage.
- `backend/setup.sh`: apply the new idempotent draft-table migration in order.
- `backend/tests/`: model, tool, orchestrator, API and PostgreSQL tests.
- `frontend/src/services/chatApi.ts`: structured response types.
- `frontend/src/services/campaignDraftApi.ts`: edit, preview and confirm requests.
- `frontend/src/components/ChatPanel.tsx`: generated-draft action.
- `frontend/src/components/CampaignBuilder.tsx`: initial draft and regeneration
  support.
- `backend/docs/api_contract.md`: endpoint and error contract.
- `backend/docs/Architecture.svg`: structured draft and confirmation flow.

## Verification

Run the relevant focused tests during each stage, then complete the repository
checks from the root:

```bash
cd backend && uv run pytest
cd ../frontend && npm run lint && npm run build
cd ..
python3 -m compileall -q backend/app backend/mcp
bash -n backend/setup.sh
terraform -chdir=backend/terraform fmt -check
```

Provision a disposable PostgreSQL instance, apply the draft migration twice to
verify idempotency and run the PostgreSQL integration tests, including forced
rollback cases. Run `terraform validate` after initialisation is available.

## Acceptance criteria

- A natural-language objective produces exactly one structured campaign draft.
- Generation retrieves no more than three approved, valid and authorised
  catalogue entries.
- The draft reports the exact reference IDs and versions it used, or explicitly
  reports that no reference was used.
- Retrieval is deterministic for the same catalogue version and request.
- Every draft passes the shared Pydantic schema before reaching the frontend.
- Invalid or ambiguous objectives produce safe errors, warnings or clarification
  questions rather than fabricated precision.
- The response includes editable fields, assumptions and targeting rationale.
- Regenerating selected sections does not change unselected fields.
- Generation and regeneration never insert, update, activate or send campaigns.
- Only an explicit confirmation for the latest adviser-owned revision creates a
  record.
- Confirmed records are created with `status = "draft"` and never automatically
  activated.
- Confirmation inserts the campaign, adviser assignment and confirmed draft
  state in one transaction and rolls all of them back on failure.
- Retrying the same confirmed request cannot create a duplicate campaign.
- Existing chat, campaign discovery, recommendation and performance tools remain
  functional.
- All deterministic backend tests, TypeScript checks and production builds pass.
- Documentation identifies generated content as AI-produced and subject to
  adviser review, suitability assessment and applicable communication-consent
  checks.

## Decisions to confirm before implementation

1. Whether `targetDemographicSummary` remains review-only metadata or becomes a
   persisted campaign field.
2. Whether the direct campaign-builder entry point is required alongside chat in
   the first release.
3. Whether confirmation creates only a draft, as proposed, or whether a separate
   activation workflow must be included in the same milestone.
4. Whether the MCP tool must support independent objective-only calls from other
   MCP clients; if so, move model generation into a shared service callable by
   both MCP and the PULSE orchestrator.
5. Who is authorised to approve, version and retire curated catalogue entries.
6. Whether the first catalogue is global synthetic reference data or scoped by
   tenant from the beginning.
7. What catalogue size or retrieval-quality threshold would justify adding
   embeddings instead of the initial metadata and lexical search.

from functools import lru_cache
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.campaigns.catalog import (
    create_campaign as create_campaign_record,
    get_campaign_record,
    list_campaigns as list_campaign_records,
    update_campaign_state,
    update_engagement_status,
    get_engagement_status,
)
from app.campaigns.models import (
    CAMPAIGN_TARGETING_FIELDS,
    CampaignCriteriaPayload,
    CampaignDraftArtifact,
    CampaignDraftField,
    CampaignDraftOptionProposal,
    CampaignDraftRegenerationRequest,
    CampaignDraftRevisionArtifact,
    CampaignDraftUpdateRequest,
    PersistedCampaignDraftArtifact,
    PersistedCampaignDraftOptionSet,
    campaign_revision_changed_fields,
)
from app.campaigns.clarification import PostgresCampaignClarificationStore
from app.campaigns.draft_repository import (
    CampaignDraftNotFound,
    CampaignDraftStaleRevision,
    CampaignDraftStorageUnavailable,
    get_campaign_draft,
    get_latest_campaign_draft,
    get_pending_campaign_draft_options,
    update_campaign_draft_revision,
)

from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN, CampaignInactive, CampaignStorageUnavailable, CampaignUnavailable,
    RequestScope, get_campaign, require_active,
)
from app.contacts.catalog import (
    ContactStorageUnavailable,
    create_contact,
    list_contacts,
    replace_contact,
)
from app.config import get_settings
from app.llm import ChatOrchestrator, LLMClient, OrchestratorResult
from app.llm.orchestrator import (
    is_active_campaign_turn_candidate,
    is_campaign_turn_candidate,
)
from app.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMToolLoopError,
)
from app.store import (
    ChatHistoryItem,
    append_exchange,
    append_exchange_with_campaign_draft,
    append_exchange_with_campaign_options,
    create_session,
    get_history,
    get_session,
    latest_session,
    list_sessions,
    now_iso,
    StoreUnavailableError,
)
from app.tools.mcp_registry import MCPToolRegistry

app = FastAPI(title="PULSE Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(CampaignStorageUnavailable)
@app.exception_handler(ContactStorageUnavailable)
@app.exception_handler(StoreUnavailableError)
@app.exception_handler(CampaignDraftStorageUnavailable)
def store_unavailable_handler(_request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(CampaignDraftNotFound)
def draft_not_found_handler(_request, exc: CampaignDraftNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(CampaignDraftStaleRevision)
def draft_stale_handler(_request, exc: CampaignDraftStaleRevision):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


class SessionResponse(BaseModel):
    session_id: str
    timestamp: str
    session_title: str
    active_campaign_draft_id: str | None = None


class NewSessionResponse(BaseModel):
    session_id: str
    timestamp: str


class HistoryResponse(BaseModel):
    timestamp: str
    user: bool | str
    message_content: str


class QueryRequest(BaseModel):
    fa_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    campaign_id: str | None = Field(default=None, pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    message_content: str = Field(min_length=1)


class QueryResponse(BaseModel):
    user: bool | str
    timestamp: str
    ai_answer: str
    campaignDraft: PersistedCampaignDraftArtifact | None = None
    campaignDraftOptions: PersistedCampaignDraftOptionSet | None = None


def _validate_revision_against_current(
    artifact: CampaignDraftRevisionArtifact,
    current: PersistedCampaignDraftArtifact,
    requested_fields: tuple[str, ...],
) -> None:
    if artifact.previousRevision != current.revision:
        raise ValueError("revision does not use the current draft")
    if artifact.objective != current.objective:
        raise ValueError("revision changed the original objective")
    if artifact.referencesUsed != current.referencesUsed:
        raise ValueError("revision changed the original citations")
    allowed_fields = campaign_revision_changed_fields(requested_fields)
    if set(artifact.changedFields) != set(allowed_fields):
        raise ValueError("revision changed an unrequested field selection")

    expected = current.draft.model_dump(mode="json")
    revised = artifact.draft.model_dump(mode="json")
    for field_name in artifact.changedFields:
        if field_name in CAMPAIGN_TARGETING_FIELDS:
            expected["criteria"][field_name] = revised["criteria"][field_name]
        else:
            expected[field_name] = revised[field_name]
    if CAMPAIGN_TARGETING_FIELDS.intersection(artifact.changedFields):
        expected["rationale"] = revised["rationale"]
    if expected != revised:
        raise ValueError("revision changed an unselected draft field")


class LeadStatsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uploaded: int = Field(ge=0)
    added: int = Field(ge=0)
    removed: int = Field(ge=0)

class StatusUpdatePayload(BaseModel):
    status: Literal[0, 1, 2]  # 0: Contacted, 1: Engaged, 2: Rejected
    campaign_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    contact_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=64)

class StatusUpdateResponse(BaseModel):
    campaign_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    contact_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=64)
    fa_id: str = Field(min_length=1, max_length=64)
    status: Literal[0, 1, 2]  # 0: Contacted, 1: Engaged, 2: Rejected

class EngagementStatusResponse(BaseModel):
    campaign_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    contact_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=64)
    fa_id: str = Field(min_length=1, max_length=64)
    status: Literal[0, 1, 2]  # 0: Contacted, 1: Engaged, 2: Rejected

class CampaignPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    name: str = Field(min_length=1, max_length=255)
    status: Literal["draft", "active", "paused", "completed"] = "active"
    startDate: date | None = None
    endDate: date | None = None
    description: str = Field(min_length=1, max_length=10_000)
    clientMessage: str = Field(min_length=1, max_length=10_000)
    bannerDataUrl: str | None = Field(default=None, max_length=1_400_000)
    origin: Literal["marketing", "advisor"]
    audienceSource: Literal["contacts", "leads"]
    channel: str | None = Field(default=None, max_length=64)
    teamIds: list[str] = Field(default_factory=list, max_length=100)
    advisorIds: list[str] = Field(default_factory=list, max_length=100)
    createdByAdvisorId: str | None = Field(default=None, max_length=64)
    criteria: CampaignCriteriaPayload
    includeIds: list[str] = Field(default_factory=list, max_length=1_000)
    excludeIds: list[str] = Field(default_factory=list, max_length=1_000)
    leadIds: list[str] = Field(default_factory=list, max_length=1_000)
    leadStats: LeadStatsPayload
    createdBy: str = Field(min_length=1, max_length=255)
    createdAt: datetime
    actions: dict[str, Literal["pipeline", "task", "dismissed"]] = Field(default_factory=dict)
    emailLog: list[dict] = Field(default_factory=list, max_length=1_000)
    leadContacts: list[dict] = Field(default_factory=list, max_length=1_000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.startDate and self.endDate and self.endDate < self.startDate:
            raise ValueError("campaign end date cannot precede start date")
        return self


class CampaignStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    includeIds: list[str] = Field(max_length=1_000)
    excludeIds: list[str] = Field(max_length=1_000)
    leadIds: list[str] = Field(max_length=1_000)
    leadStats: LeadStatsPayload
    actions: dict[str, Literal["pipeline", "task", "dismissed"]]
    emailLog: list[dict] = Field(max_length=1_000)
    leadContacts: list[dict] = Field(max_length=1_000)


class ContactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(max_length=320)
    countryCode: str = Field(default="+65", max_length=8)
    phone: str = Field(default="", max_length=32)
    dob: date | None = None
    gender: Literal["male", "female"] | None = None
    cashAmount: float | None = Field(default=None, ge=0)
    label: Literal["Prospect", "Client"] | None = None
    status: Literal["lead", "contact"] = "contact"
    bookmarked: bool = False
    needsAttention: bool = False
    optInEmail: bool = False
    optInSms: bool = False
    nric: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=20_000)
    meetings: list[dict] = Field(default_factory=list, max_length=1_000)
    profile: dict | None = None
    policies: list[dict] = Field(default_factory=list, max_length=1_000)
    lastContacted: str | None = Field(default=None, max_length=32)
    source: Literal["own", "transferred", "canvassed", "referral"] | None = None
    transferredFrom: str | None = Field(default=None, max_length=255)
    transferredOn: str | None = Field(default=None, max_length=32)
    introduced: bool | None = None


@lru_cache
def get_orchestrator() -> ChatOrchestrator:
    settings = get_settings()
    return ChatOrchestrator(
        LLMClient(settings),
        settings,
        registry=MCPToolRegistry(settings.mcp_server_url),
        clarification_store=PostgresCampaignClarificationStore(),
    )


@app.get("/health")
def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "llm_model": settings.llm_model,
    }


def _contact_scope(fa_id: str) -> RequestScope:
    advisor_id = fa_id.strip()
    if not advisor_id:
        raise HTTPException(status_code=400, detail="fa_id is required for contacts")
    return RequestScope(advisor_id)


@app.get("/contacts", response_model=list[ContactPayload])
@app.get("/api/contacts", response_model=list[ContactPayload])
def contacts_list(fa_id: str = Query(min_length=1)) -> list[ContactPayload]:
    return [ContactPayload.model_validate(row)
            for row in list_contacts(_contact_scope(fa_id))]


@app.post("/contacts", response_model=ContactPayload, status_code=201)
@app.post("/api/contacts", response_model=ContactPayload, status_code=201)
def contact_create(payload: ContactPayload,
                   fa_id: str = Query(min_length=1)) -> ContactPayload:
    try:
        row = create_contact(_contact_scope(fa_id), payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ContactPayload.model_validate(row)


@app.put("/contacts/{contact_id}", response_model=ContactPayload)
@app.put("/api/contacts/{contact_id}", response_model=ContactPayload)
def contact_replace(
    contact_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN, max_length=64)],
    payload: ContactPayload,
    fa_id: str = Query(min_length=1),
) -> ContactPayload:
    if payload.id != contact_id:
        raise HTTPException(status_code=400, detail="contact ID does not match path")
    row = replace_contact(_contact_scope(fa_id), contact_id, payload.model_dump())
    if row is None:
        raise HTTPException(status_code=404, detail="contact not found")
    return ContactPayload.model_validate(row)


def _campaign_scope(role: Literal["advisor", "marketing"],
                    fa_id: str | None) -> RequestScope | None:
    if role == "marketing":
        return None
    advisor_id = (fa_id or "").strip()
    if not advisor_id:
        raise HTTPException(status_code=400, detail="fa_id is required for adviser campaigns")
    return RequestScope(advisor_id)


@app.get("/campaigns", response_model=list[CampaignPayload])
@app.get("/api/campaigns", response_model=list[CampaignPayload])
def campaigns_list(
    role: Literal["advisor", "marketing"] = Query(),
    fa_id: str | None = Query(default=None, min_length=1),
) -> list[CampaignPayload]:
    scope = _campaign_scope(role, fa_id)
    return [CampaignPayload.model_validate(row)
            for row in list_campaign_records(role, scope)]


@app.get("/campaigns/engagement-status", response_model=EngagementStatusResponse | None)
@app.get("/api/campaigns/engagement-status", response_model=EngagementStatusResponse | None)
def campaign_engagement_status(
    campaign_id: Annotated[str, Query(pattern=CAMPAIGN_ID_PATTERN, max_length=69)],
    fa_id: str = Query(min_length=1),
    contact_id: str = Query(min_length=1),
) -> EngagementStatusResponse | None:
    row = get_engagement_status(fa_id, campaign_id, contact_id)
    return EngagementStatusResponse.model_validate(row) if row is not None else None


@app.get("/campaigns/{campaign_id}", response_model=CampaignPayload)
@app.get("/api/campaigns/{campaign_id}", response_model=CampaignPayload)
def campaign_detail(
    campaign_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN, max_length=69)],
    role: Literal["advisor", "marketing"] = Query(),
    fa_id: str | None = Query(default=None, min_length=1),
) -> CampaignPayload:
    scope = _campaign_scope(role, fa_id)
    row = get_campaign_record(role, scope, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return CampaignPayload.model_validate(row)


@app.post("/campaigns", response_model=CampaignPayload, status_code=201)
@app.post("/api/campaigns", response_model=CampaignPayload, status_code=201)
def campaign_create(
    payload: CampaignPayload,
    role: Literal["advisor", "marketing"] = Query(),
    fa_id: str | None = Query(default=None, min_length=1),
) -> CampaignPayload:
    scope = _campaign_scope(role, fa_id)
    expected_origin = "advisor" if role == "advisor" else "marketing"
    if payload.origin != expected_origin:
        raise HTTPException(status_code=400, detail="campaign origin does not match current role")
    try:
        row = create_campaign_record(role, scope, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CampaignPayload.model_validate(row)


@app.patch("/campaigns/{campaign_id}/state", response_model=CampaignPayload)
@app.patch("/api/campaigns/{campaign_id}/state", response_model=CampaignPayload)
def campaign_state_update(
    campaign_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN, max_length=69)],
    payload: CampaignStatePayload,
    role: Literal["advisor", "marketing"] = Query(),
    fa_id: str | None = Query(default=None, min_length=1),
) -> CampaignPayload:
    scope = _campaign_scope(role, fa_id)
    try:
        row = update_campaign_state(role, scope, campaign_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return CampaignPayload.model_validate(row)

@app.post("/campaign/update-engagement-status", response_model=StatusUpdateResponse, status_code=201)
@app.post("/api/campaign/update-engagement-status", response_model=StatusUpdateResponse, status_code=201)
def campaign_update_status(
    payload: StatusUpdatePayload,
    fa_id: str | None = Query(default=None, min_length=1),
) -> StatusUpdateResponse:
    advisor_id = (fa_id or "").strip()
    if not advisor_id:
        raise HTTPException(status_code=400, detail="fa_id is required")
    try:
        row = update_engagement_status(
            advisor_id,
            payload.campaign_id,
            payload.contact_id,
            payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="campaign or client not found")
    return StatusUpdateResponse.model_validate(row)

@app.get("/chat/sessions", response_model=list[SessionResponse])
@app.get("/api/chat/sessions", response_model=list[SessionResponse])
def chat_sessions(fa_id: str = Query(min_length=1)) -> list[SessionResponse]:
    return [
        SessionResponse(
            session_id=session.session_id,
            timestamp=session.timestamp,
            session_title=session.session_title,
            active_campaign_draft_id=session.active_campaign_draft_id,
        )
        for session in list_sessions(fa_id)
    ]


@app.post("/chat/new", response_model=NewSessionResponse)
@app.post("/api/chat/new", response_model=NewSessionResponse)
def chat_new(fa_id: str = Query(min_length=1)) -> NewSessionResponse:
    session = create_session(fa_id)
    return NewSessionResponse(session_id=session.session_id, timestamp=session.timestamp)


@app.get("/chat/history", response_model=list[HistoryResponse])
@app.get("/api/chat/history", response_model=list[HistoryResponse])
def chat_history(session_id: str = Query(min_length=1)) -> list[HistoryResponse]:
    history = get_history(session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    return [HistoryResponse(**item.__dict__) for item in history]


CampaignDraftId = Annotated[
    str,
    Path(
        min_length=36,
        max_length=36,
        pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
    ),
]


def _review_campaign_draft(
    draft_id: str, fa_id: str, session_id: str
) -> tuple[RequestScope, PersistedCampaignDraftArtifact]:
    advisor_id = fa_id.strip()
    active_session = get_session(session_id)
    if active_session is None or active_session.fa_id != advisor_id:
        raise HTTPException(status_code=404, detail="campaign draft not found")
    scope = RequestScope(advisor_id)
    current = get_campaign_draft(scope, session_id, draft_id)
    if current is None:
        raise HTTPException(status_code=404, detail="campaign draft not found")
    if current.status not in {"generated", "reviewed"}:
        raise HTTPException(status_code=409, detail="campaign draft is not reviewable")
    return scope, current


def _run_campaign_draft_review_revision(
    *,
    current: PersistedCampaignDraftArtifact,
    scope: RequestScope,
    session_id: str,
    fields: tuple[CampaignDraftField, ...],
    instruction: str,
    proposed_changes: dict | None = None,
) -> CampaignDraftRevisionArtifact:
    try:
        result = get_orchestrator().revise_campaign_draft(
            current_draft=current,
            fields=fields,
            instruction=instruction,
            scope=scope,
            session_id=session_id,
            proposed_changes=proposed_changes,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMAuthenticationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (LLMProviderError, LLMToolLoopError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not isinstance(result, OrchestratorResult) or len(result.artifacts) != 1:
        detail = result.answer if isinstance(result, OrchestratorResult) else None
        raise HTTPException(
            status_code=422,
            detail=detail or "campaign draft revision failed validation",
        )
    artifact = result.artifacts[0]
    if not isinstance(artifact, CampaignDraftRevisionArtifact):
        raise HTTPException(status_code=502, detail="campaign draft revision is invalid")
    try:
        _validate_revision_against_current(artifact, current, fields)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="campaign draft revision is invalid") from exc
    return artifact


@app.get(
    "/campaign-drafts/{draft_id}", response_model=PersistedCampaignDraftArtifact
)
@app.get(
    "/api/campaign-drafts/{draft_id}", response_model=PersistedCampaignDraftArtifact
)
def campaign_draft_get(
    draft_id: CampaignDraftId,
    fa_id: str = Query(min_length=1, max_length=64),
    session_id: str = Query(min_length=1, max_length=64),
) -> PersistedCampaignDraftArtifact:
    _scope, current = _review_campaign_draft(draft_id, fa_id, session_id)
    return current


@app.patch(
    "/campaign-drafts/{draft_id}", response_model=PersistedCampaignDraftArtifact
)
@app.patch(
    "/api/campaign-drafts/{draft_id}", response_model=PersistedCampaignDraftArtifact
)
def campaign_draft_update(
    draft_id: CampaignDraftId,
    payload: CampaignDraftUpdateRequest,
) -> PersistedCampaignDraftArtifact:
    scope, current = _review_campaign_draft(
        draft_id, payload.fa_id, payload.session_id
    )
    if current.revision != payload.expectedRevision:
        raise CampaignDraftStaleRevision("campaign draft revision is stale")
    selected = payload.changes.model_fields_set
    fields = tuple(
        field for field in CampaignDraftField.__args__ if field in selected
    )
    changes = payload.changes.model_dump(include=selected, exclude_none=True)
    artifact = _run_campaign_draft_review_revision(
        current=current,
        scope=scope,
        session_id=payload.session_id,
        fields=fields,
        instruction="Apply the adviser's structured review edits exactly.",
        proposed_changes=changes,
    )
    return update_campaign_draft_revision(
        scope,
        payload.session_id,
        draft_id,
        payload.expectedRevision,
        artifact,
        status="reviewed",
    )


@app.post(
    "/campaign-drafts/{draft_id}/regenerate",
    response_model=PersistedCampaignDraftArtifact,
)
@app.post(
    "/api/campaign-drafts/{draft_id}/regenerate",
    response_model=PersistedCampaignDraftArtifact,
)
def campaign_draft_regenerate(
    draft_id: CampaignDraftId,
    payload: CampaignDraftRegenerationRequest,
) -> PersistedCampaignDraftArtifact:
    scope, current = _review_campaign_draft(
        draft_id, payload.fa_id, payload.session_id
    )
    if current.revision != payload.expectedRevision:
        raise CampaignDraftStaleRevision("campaign draft revision is stale")
    fields = tuple(payload.fields)
    artifact = _run_campaign_draft_review_revision(
        current=current,
        scope=scope,
        session_id=payload.session_id,
        fields=fields,
        instruction=payload.instruction,
    )
    return update_campaign_draft_revision(
        scope,
        payload.session_id,
        draft_id,
        payload.expectedRevision,
        artifact,
        status="reviewed",
    )


@app.post("/chat/query", response_model=QueryResponse)
@app.post("/api/chat/query", response_model=QueryResponse)
def chat_query(
    payload: QueryRequest,
    fa_id: str | None = Query(default=None, min_length=1),
) -> QueryResponse:
    advisor_id = (fa_id or payload.fa_id or "").strip()
    if not advisor_id:
        raise HTTPException(status_code=400, detail="fa_id is required")

    message_content = payload.message_content.strip()
    if not message_content:
        raise HTTPException(status_code=422, detail="message_content must not be empty")

    # Tenant is fixed by the synthetic adapter, not chosen by the model/client.
    # fa_id remains caller-supplied until real authentication is introduced.
    scope = RequestScope(advisor_id)
    if payload.campaign_id is not None:
        try:
            require_active(get_campaign(payload.campaign_id, scope))
        except CampaignUnavailable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CampaignInactive as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload.session_id:
        session = get_session(payload.session_id)
        if session is None or session.fa_id != advisor_id:
            raise HTTPException(status_code=404, detail="chat session not found")
    else:
        session = latest_session(advisor_id) or create_session(advisor_id)

    history = get_history(session.session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="chat session not found")

    campaign_turn_candidate = is_campaign_turn_candidate(message_content)
    active_campaign_turn_candidate = is_active_campaign_turn_candidate(
        message_content
    )
    current_draft = None
    if (
        session.active_campaign_draft_id is not None
        and active_campaign_turn_candidate
    ):
        current_draft = get_campaign_draft(
            scope, session.session_id, session.active_campaign_draft_id
        )
        if current_draft is not None and current_draft.status not in {
            "generated", "reviewed"
        }:
            current_draft = None
    if campaign_turn_candidate and current_draft is None:
        # Compatibility for rows created before the active pointer existed,
        # and for a pointer whose draft is no longer reviewable.
        current_draft = get_latest_campaign_draft(scope, session.session_id)
    pending_draft_options = (
        get_pending_campaign_draft_options(
            scope,
            session.session_id,
            current_draft.draftId,
            current_draft.revision,
        )
        if current_draft is not None
        else None
    )
    revision_context_checked = campaign_turn_candidate or current_draft is not None

    try:
        orchestration_context = {
            "scope": scope,
            "campaign_id": payload.campaign_id,
            "session_id": session.session_id,
        }
        if revision_context_checked:
            orchestration_context.update({
                "current_draft": current_draft,
                "pending_draft_options": pending_draft_options,
                "revision_context_checked": True,
            })
        result = get_orchestrator().run(message_content, history, **orchestration_context)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMAuthenticationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (LLMProviderError, LLMToolLoopError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not isinstance(result, OrchestratorResult):
        raise HTTPException(status_code=502, detail="LLM orchestrator returned an invalid result")
    if len(result.artifacts) > 1:
        raise HTTPException(status_code=502, detail="LLM orchestrator returned ambiguous artifacts")
    has_option_set = result.selected_option_set_id is not None
    has_option_number = result.selected_option_number is not None
    if has_option_set != has_option_number:
        raise HTTPException(
            status_code=502, detail="LLM orchestrator returned invalid option metadata"
        )
    if not result.artifacts and (
        has_option_set or result.requested_revision_fields
    ):
        raise HTTPException(
            status_code=502, detail="LLM orchestrator returned orphaned draft metadata"
        )

    artifact: (
        CampaignDraftArtifact | CampaignDraftRevisionArtifact
        | CampaignDraftOptionProposal | None
    ) = None
    if result.artifacts:
        candidate = result.artifacts[0]
        try:
            if isinstance(candidate, CampaignDraftRevisionArtifact):
                artifact = CampaignDraftRevisionArtifact.model_validate(
                    candidate.model_dump(mode="json")
                )
                if current_draft is None:
                    raise ValueError("revision is missing its authoritative source")
                _validate_revision_against_current(
                    artifact,
                    current_draft,
                    result.requested_revision_fields,
                )
            elif isinstance(candidate, CampaignDraftOptionProposal):
                if has_option_set or result.requested_revision_fields:
                    raise ValueError("campaign options include revision metadata")
                artifact = CampaignDraftOptionProposal.model_validate(
                    candidate.model_dump(mode="json")
                )
                if current_draft is None:
                    raise ValueError("campaign options are missing their current draft")
                if artifact.baseRevision != current_draft.revision:
                    raise ValueError("campaign options use a stale revision")
            elif isinstance(candidate, CampaignDraftArtifact):
                if has_option_set or result.requested_revision_fields:
                    raise ValueError("new campaign draft includes revision metadata")
                artifact = CampaignDraftArtifact.model_validate(
                    candidate.model_dump(mode="json")
                )
            else:
                raise ValueError("unsupported artifact")
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=502, detail="LLM orchestrator returned an invalid artifact"
            ) from exc

    ai_answer = result.answer

    user_item = ChatHistoryItem(
        timestamp=now_iso(),
        user=advisor_id,
        message_content=message_content,
    )
    assistant_item = ChatHistoryItem(
        timestamp=now_iso(),
        user=False,
        message_content=ai_answer,
    )
    persisted_draft = None
    persisted_options = None
    if artifact is None:
        append_exchange(session.session_id, user_item, assistant_item)
    elif isinstance(artifact, CampaignDraftOptionProposal):
        persisted_options = append_exchange_with_campaign_options(
            session.session_id,
            user_item,
            assistant_item,
            scope,
            current_draft.draftId,
            artifact,
        )
    else:
        persisted_draft = append_exchange_with_campaign_draft(
            session.session_id,
            user_item,
            assistant_item,
            scope,
            artifact,
            draft_id=current_draft.draftId if current_draft else None,
            expected_revision=current_draft.revision if current_draft else None,
            selected_option_set_id=result.selected_option_set_id,
            selected_option_number=result.selected_option_number,
        )

    return QueryResponse(
        user=advisor_id,
        timestamp=assistant_item.timestamp,
        ai_answer=ai_answer,
        campaignDraft=persisted_draft,
        campaignDraftOptions=persisted_options,
    )

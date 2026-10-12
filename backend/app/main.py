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
from app.llm import ChatOrchestrator, LLMClient
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
def store_unavailable_handler(_request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


class SessionResponse(BaseModel):
    session_id: str
    timestamp: str
    session_title: str


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


class NumericRangePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_order(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("range minimum cannot exceed maximum")
        return self


class CampaignCriteriaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ageGroups: list[Literal["under35", "35to44", "45to54", "55to64", "65plus"]]
    ageRange: NumericRangePayload | None = None
    genders: list[Literal["male", "female"]]
    cashBands: list[Literal["under50k", "50kTo250k", "250kTo1m", "above1m"]]
    cashRange: NumericRangePayload | None = None


class LeadStatsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uploaded: int = Field(ge=0)
    added: int = Field(ge=0)
    removed: int = Field(ge=0)


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


@app.get("/chat/sessions", response_model=list[SessionResponse])
@app.get("/api/chat/sessions", response_model=list[SessionResponse])
def chat_sessions(fa_id: str = Query(min_length=1)) -> list[SessionResponse]:
    return [
        SessionResponse(
            session_id=session.session_id,
            timestamp=session.timestamp,
            session_title=session.session_title,
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

    try:
        ai_answer = get_orchestrator().run(
            message_content, history, scope=scope, campaign_id=payload.campaign_id,
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
    append_exchange(session.session_id, user_item, assistant_item)

    return QueryResponse(
        user=advisor_id,
        timestamp=assistant_item.timestamp,
        ai_answer=ai_answer,
    )

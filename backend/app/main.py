from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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

app = FastAPI(title="PULSE Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(StoreUnavailableError)
def store_unavailable_handler(_request, exc: StoreUnavailableError):
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
    message_content: str = Field(min_length=1)


class QueryResponse(BaseModel):
    user: bool | str
    timestamp: str
    ai_answer: str


@lru_cache
def get_orchestrator() -> ChatOrchestrator:
    settings = get_settings()
    return ChatOrchestrator(LLMClient(settings), settings)


@app.get("/health")
def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "llm_model": settings.llm_model,
    }


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
    advisor_id = fa_id or payload.fa_id
    if not advisor_id:
        raise HTTPException(status_code=400, detail="fa_id is required")

    message_content = payload.message_content.strip()
    if not message_content:
        raise HTTPException(status_code=422, detail="message_content must not be empty")

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
        ai_answer = get_orchestrator().run(message_content, history)
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

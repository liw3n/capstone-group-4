from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel, Field

from .store import (
    ChatHistoryItem,
    append_history,
    create_session,
    get_history,
    latest_session,
    list_sessions,
    now_iso,
)

app = FastAPI(title="MyWealth Chat API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
    message_content: str = Field(min_length=1)


class QueryResponse(BaseModel):
    user: bool | str
    timestamp: str
    ai_answer: str


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

    session = latest_session(advisor_id) or create_session(advisor_id)
    append_history(
        session.session_id,
        ChatHistoryItem(
            timestamp=now_iso(),
            user=advisor_id,
            message_content=message_content,
        ),
    )

    ai_answer = "Thanks for your message. I can help review campaign reach and outstanding actions."
    append_history(
        session.session_id,
        ChatHistoryItem(
            timestamp=now_iso(),
            user=False,
            message_content=ai_answer,
        ),
    )
    return QueryResponse(user=advisor_id, timestamp=now_iso(), ai_answer=ai_answer)


handler = Mangum(app)

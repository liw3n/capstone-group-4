from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class ChatSession:
    session_id: str
    fa_id: str
    timestamp: str
    session_title: str = "New chat"


@dataclass
class ChatHistoryItem:
    timestamp: str
    user: bool | str
    message_content: str


_sessions: dict[str, ChatSession] = {}
_history: dict[str, list[ChatHistoryItem]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def list_sessions(fa_id: str) -> list[ChatSession]:
    return sorted(
        (session for session in _sessions.values() if session.fa_id == fa_id),
        key=lambda session: session.timestamp,
        reverse=True,
    )


def create_session(fa_id: str) -> ChatSession:
    session = ChatSession(
        session_id=str(uuid4()),
        fa_id=fa_id,
        timestamp=now_iso(),
    )
    _sessions[session.session_id] = session
    _history[session.session_id] = []
    return session


def latest_session(fa_id: str) -> ChatSession | None:
    sessions = list_sessions(fa_id)
    return sessions[0] if sessions else None


def get_history(session_id: str) -> list[ChatHistoryItem] | None:
    return _history.get(session_id)


def append_history(session_id: str, item: ChatHistoryItem) -> None:
    if session_id in _history:
        _history[session_id].append(item)

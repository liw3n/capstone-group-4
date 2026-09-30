from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT session_id, timestamp, COALESCE(session_title, 'New chat') AS session_title
            FROM campaign_chat_sessions
            WHERE fa_id = %s
            ORDER BY timestamp DESC
            """,
            (fa_id,),
        ).fetchall()

    return [
        ChatSession(
            session_id=row["session_id"],
            fa_id=str(fa_id),
            timestamp=row["timestamp"].isoformat(),
            session_title=row["session_title"],
        )
        for row in rows
    ]


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

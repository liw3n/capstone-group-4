from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings
from app.campaigns.models import (
    CampaignDraftArtifact,
    CampaignDraftOptionProposal,
    CampaignDraftRevisionArtifact,
)
from app.campaigns.repository import RequestScope


@dataclass
class ChatSession:
    session_id: str
    fa_id: str
    timestamp: str
    session_title: str = "New chat"
    active_campaign_draft_id: str | None = None


@dataclass
class ChatHistoryItem:
    timestamp: str
    user: bool | str
    message_content: str


class StoreUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot complete a storage operation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise StoreUnavailableError("DATABASE_URL is not configured")
    return database_url


def _timestamp_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def _connection():
    try:
        with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
            yield connection
    except StoreUnavailableError:
        raise
    except psycopg.Error as exc:
        raise StoreUnavailableError("chat storage is temporarily unavailable") from exc


def _session_from_row(row: dict) -> ChatSession:
    return ChatSession(
        session_id=row["session_id"],
        fa_id=row["fa_id"],
        timestamp=_timestamp_iso(row["timestamp"]),
        session_title=row["session_title"] or "New chat",
        active_campaign_draft_id=row.get("active_campaign_draft_id"),
    )


def list_sessions(fa_id: str) -> list[ChatSession]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT session_id, fa_id, timestamp, session_title, active_campaign_draft_id
            FROM campaign_chat_sessions
            WHERE fa_id = %s
            ORDER BY timestamp DESC
            """,
            (fa_id,),
        ).fetchall()
    return [_session_from_row(row) for row in rows]


def get_session(session_id: str) -> ChatSession | None:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT session_id, fa_id, timestamp, session_title, active_campaign_draft_id
            FROM campaign_chat_sessions
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()
    return _session_from_row(row) if row else None


def create_session(fa_id: str) -> ChatSession:
    session_id = str(uuid4())
    with _connection() as connection:
        row = connection.execute(
            """
            INSERT INTO campaign_chat_sessions (session_id, fa_id, session_title)
            VALUES (%s, %s, %s)
            RETURNING session_id, fa_id, timestamp, session_title, active_campaign_draft_id
            """,
            (session_id, fa_id, "New chat"),
        ).fetchone()
    return _session_from_row(row)


def latest_session(fa_id: str) -> ChatSession | None:
    sessions = list_sessions(fa_id)
    return sessions[0] if sessions else None


def get_history(session_id: str) -> list[ChatHistoryItem] | None:
    with _connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM campaign_chat_sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
        if not exists:
            return None

        rows = connection.execute(
            """
            SELECT timestamp, role, user_id, message_content
            FROM campaign_chat_messages
            WHERE session_id = %s
            ORDER BY timestamp ASC, message_id ASC
            """,
            (session_id,),
        ).fetchall()

    return [
        ChatHistoryItem(
            timestamp=_timestamp_iso(row["timestamp"]),
            user=False if row["role"] == "assistant" else row["user_id"],
            message_content=row["message_content"],
        )
        for row in rows
    ]


def append_history(session_id: str, item: ChatHistoryItem) -> None:
    role = "assistant" if item.user is False else "user"
    user_id = None if item.user is False else str(item.user)
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO campaign_chat_messages
                (session_id, timestamp, role, user_id, message_content)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, item.timestamp, role, user_id, item.message_content),
        )


def append_exchange(
    session_id: str,
    user_item: ChatHistoryItem,
    assistant_item: ChatHistoryItem,
) -> None:
    """Persist one user/assistant exchange atomically."""
    with _connection() as connection:
        _append_exchange(connection, session_id, user_item, assistant_item)


def _append_exchange(
    connection,
    session_id: str,
    user_item: ChatHistoryItem,
    assistant_item: ChatHistoryItem,
) -> None:
    session_title = " ".join(user_item.message_content.split()[:5]) + "..."
    connection.execute(
        """
        INSERT INTO campaign_chat_messages
            (session_id, timestamp, role, user_id, message_content)
        VALUES (%s, %s, 'user', %s, %s)
        """,
        (
            session_id,
            user_item.timestamp,
            str(user_item.user),
            user_item.message_content,
        ),
    )
    connection.execute(
        """
        UPDATE campaign_chat_sessions
        SET session_title = %s
        WHERE session_id = %s
          AND (session_title IS NULL OR session_title = 'New chat')
        """,
        (session_title, session_id),
    )
    connection.execute(
        """
        INSERT INTO campaign_chat_messages
            (session_id, timestamp, role, user_id, message_content)
        VALUES (%s, %s, 'assistant', NULL, %s)
        """,
        (session_id, assistant_item.timestamp, assistant_item.message_content),
    )


def append_exchange_with_campaign_draft(
    session_id: str,
    user_item: ChatHistoryItem,
    assistant_item: ChatHistoryItem,
    scope: RequestScope,
    artifact: CampaignDraftArtifact | CampaignDraftRevisionArtifact,
    *,
    draft_id: str | None = None,
    expected_revision: int | None = None,
    selected_option_set_id: str | None = None,
    selected_option_number: int | None = None,
):
    """Atomically persist a chat exchange and its generated/revised draft."""
    from app.campaigns.draft_repository import (
        create_campaign_draft,
        mark_campaign_draft_option_selected,
        update_campaign_draft_revision,
    )

    with _connection() as connection:
        _append_exchange(connection, session_id, user_item, assistant_item)
        if isinstance(artifact, CampaignDraftRevisionArtifact):
            if draft_id is None or expected_revision is None:
                raise ValueError("current campaign draft context is required")
            if selected_option_set_id is not None:
                if selected_option_number is None:
                    raise ValueError("selected option number is required")
                mark_campaign_draft_option_selected(
                    scope,
                    session_id,
                    draft_id,
                    expected_revision,
                    selected_option_set_id,
                    selected_option_number,
                    connection=connection,
                )
            return update_campaign_draft_revision(
                scope,
                session_id,
                draft_id,
                expected_revision,
                artifact,
                connection=connection,
            )
        return create_campaign_draft(
            scope, session_id, artifact, connection=connection
        )


def append_exchange_with_campaign_options(
    session_id: str,
    user_item: ChatHistoryItem,
    assistant_item: ChatHistoryItem,
    scope: RequestScope,
    draft_id: str,
    proposal: CampaignDraftOptionProposal,
):
    """Atomically persist an exchange and its revision-bound structured options."""
    from app.campaigns.draft_repository import create_campaign_draft_option_set

    with _connection() as connection:
        _append_exchange(connection, session_id, user_item, assistant_item)
        return create_campaign_draft_option_set(
            scope,
            session_id,
            draft_id,
            proposal,
            connection=connection,
        )

"""Scoped PostgreSQL persistence for review-only campaign draft revisions."""

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config
from app.campaigns.models import (
    CampaignDraftArtifact,
    CampaignDraftRevisionArtifact,
    PersistedCampaignDraftArtifact,
)
from app.campaigns.repository import RequestScope


class CampaignDraftStorageUnavailable(RuntimeError):
    """Raised when campaign draft persistence cannot be completed safely."""


class CampaignDraftNotFound(ValueError):
    """Raised for missing and cross-scope drafts without revealing ownership."""


class CampaignDraftStaleRevision(ValueError):
    """Raised when an update is based on a superseded revision."""


def _timestamp_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def draft_transaction():
    database_url = config.get_settings().database_url
    if not database_url:
        raise CampaignDraftStorageUnavailable("campaign draft storage is not configured")
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            yield connection
    except CampaignDraftStorageUnavailable:
        raise
    except psycopg.Error as exc:
        raise CampaignDraftStorageUnavailable(
            "campaign draft storage is temporarily unavailable"
        ) from exc


def _from_row(row: dict) -> PersistedCampaignDraftArtifact:
    # Reading the timestamps here ensures malformed database rows fail at this
    # trusted boundary even though Stage 7 does not expose them over HTTP.
    _timestamp_iso(row["created_at"])
    _timestamp_iso(row["updated_at"])
    return PersistedCampaignDraftArtifact.model_validate({
        "draftId": row["draft_id"],
        "objective": row["objective"],
        "referencesUsed": row["references_used"],
        "draft": row["draft"],
        "revision": row["revision"],
        "status": row["status"],
        "changedFields": row["changed_fields"],
        "validation": row["validation"],
    })


_RETURNING = """
    draft_id, objective, references_used, draft, validation,
    revision, status, changed_fields, created_at, updated_at
"""


def get_campaign_draft(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    *,
    connection=None,
) -> PersistedCampaignDraftArtifact | None:
    def read(active_connection):
        return active_connection.execute(
            f"""
            SELECT {_RETURNING}
            FROM campaign_generation_drafts
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s
            """,
            (draft_id, scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()

    if connection is not None:
        row = read(connection)
    else:
        with draft_transaction() as active_connection:
            row = read(active_connection)
    return _from_row(row) if row else None


def get_latest_campaign_draft(
    scope: RequestScope,
    session_id: str,
    *,
    connection=None,
) -> PersistedCampaignDraftArtifact | None:
    def read(active_connection):
        return active_connection.execute(
            f"""
            SELECT {_RETURNING}
            FROM campaign_generation_drafts
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND status IN ('generated', 'reviewed')
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()

    if connection is not None:
        row = read(connection)
    else:
        with draft_transaction() as active_connection:
            row = read(active_connection)
    return _from_row(row) if row else None


def create_campaign_draft(
    scope: RequestScope,
    session_id: str,
    artifact: CampaignDraftArtifact,
    *,
    connection=None,
) -> PersistedCampaignDraftArtifact:
    draft_id = str(uuid4())
    model_version = getattr(config.get_settings(), "llm_model", None)

    def create(active_connection):
        row = active_connection.execute(
            f"""
            INSERT INTO campaign_generation_drafts
                (draft_id, tenant_id, fa_id, session_id, objective,
                 references_used, draft, validation, revision, status,
                 changed_fields, model_version, prompt_version)
            SELECT %s, %s, %s, sessions.session_id, %s, %s, %s, %s,
                   1, 'generated', ARRAY[]::TEXT[], %s, 'stage-7-v1'
            FROM campaign_chat_sessions AS sessions
            WHERE sessions.session_id = %s AND sessions.fa_id = %s
            RETURNING {_RETURNING}
            """,
            (
                draft_id,
                scope.tenant_id,
                scope.fa_id,
                artifact.objective,
                Jsonb([item.model_dump(mode="json") for item in artifact.referencesUsed]),
                Jsonb(artifact.draft.model_dump(mode="json")),
                Jsonb(artifact.validation.model_dump(mode="json")),
                model_version,
                session_id,
                scope.fa_id,
            ),
        ).fetchone()
        return row

    if connection is not None:
        row = create(connection)
    else:
        with draft_transaction() as active_connection:
            row = create(active_connection)
    if row is None:
        raise CampaignDraftNotFound("campaign draft session not found")
    return _from_row(row)


def update_campaign_draft_revision(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    expected_revision: int,
    artifact: CampaignDraftRevisionArtifact,
    *,
    connection=None,
) -> PersistedCampaignDraftArtifact:
    if artifact.previousRevision != expected_revision:
        raise CampaignDraftStaleRevision("campaign draft revision is stale")
    if artifact.revision != expected_revision + 1:
        raise CampaignDraftStaleRevision("campaign draft revision must advance once")

    def update(active_connection):
        row = active_connection.execute(
            f"""
            UPDATE campaign_generation_drafts
            SET objective = %s, references_used = %s, draft = %s,
                validation = %s, revision = %s, status = 'generated',
                changed_fields = %s, updated_at = CURRENT_TIMESTAMP
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND revision = %s
              AND status IN ('generated', 'reviewed')
            RETURNING {_RETURNING}
            """,
            (
                artifact.objective,
                Jsonb([item.model_dump(mode="json") for item in artifact.referencesUsed]),
                Jsonb(artifact.draft.model_dump(mode="json")),
                Jsonb(artifact.validation.model_dump(mode="json")),
                artifact.revision,
                list(artifact.changedFields),
                draft_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                expected_revision,
            ),
        ).fetchone()
        if row is not None:
            return row
        scoped = active_connection.execute(
            """
            SELECT revision
            FROM campaign_generation_drafts
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s
            """,
            (draft_id, scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()
        if scoped is None:
            raise CampaignDraftNotFound("campaign draft not found")
        raise CampaignDraftStaleRevision("campaign draft revision is stale")

    if connection is not None:
        row = update(connection)
    else:
        with draft_transaction() as active_connection:
            row = update(active_connection)
    return _from_row(row)

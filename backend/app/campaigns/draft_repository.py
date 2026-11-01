"""Scoped PostgreSQL persistence and atomic campaign-draft confirmation."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config
from app.campaigns.models import (
    CampaignDraftArtifact,
    CampaignDraftCreationMetadata,
    CampaignDraftOptionProposal,
    CampaignDraftRevisionArtifact,
    PersistedCampaignDraftArtifact,
    PersistedCampaignDraftOptionSet,
)
from app.campaigns.criteria import criteria_to_storage
from app.campaigns.repository import RequestScope, _storage_tenant_id


class CampaignDraftStorageUnavailable(RuntimeError):
    """Raised when campaign draft persistence cannot be completed safely."""


class CampaignDraftNotFound(ValueError):
    """Raised for missing and cross-scope drafts without revealing ownership."""


class CampaignDraftStaleRevision(ValueError):
    """Raised when an update is based on a superseded revision."""


class CampaignDraftConfirmationConflict(ValueError):
    """Raised when a confirmation cannot safely create exactly one campaign."""


@dataclass(frozen=True)
class CampaignDraftPreviewMetadata:
    content_hash: str
    revision: int
    token_digest: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class CampaignDraftConfirmationResult:
    campaign_id: str
    created: bool


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
        "creation": row.get("creation_metadata") or {
            "startDate": None,
            "endDate": None,
            "audienceSource": "contacts",
        },
        "revision": row["revision"],
        "status": row["status"],
        "changedFields": row["changed_fields"],
        "validation": row["validation"],
    })


def _option_from_row(row: dict) -> PersistedCampaignDraftOptionSet:
    return PersistedCampaignDraftOptionSet.model_validate({
        "optionSetId": row["option_set_id"],
        "draftId": row["draft_id"],
        "baseRevision": row["base_revision"],
        "field": row["field_name"],
        "options": row["options"],
        "status": row["status"],
        "expiresAt": row["expires_at"],
    })


_RETURNING = """
    draft_id, objective, references_used, draft, creation_metadata, validation,
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


def get_campaign_draft_preview_metadata(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    *,
    connection=None,
) -> CampaignDraftPreviewMetadata | None:
    def read(active_connection):
        return active_connection.execute(
            """
            SELECT preview_content_hash, preview_revision, preview_token_digest,
                   preview_created_at, preview_expires_at
            FROM campaign_generation_drafts
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND status IN ('generated', 'reviewed')
            """,
            (draft_id, scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()

    if connection is not None:
        row = read(connection)
    else:
        with draft_transaction() as active_connection:
            row = read(active_connection)
    if row is None or any(
        row[field] is None
        for field in (
            "preview_content_hash",
            "preview_revision",
            "preview_token_digest",
            "preview_created_at",
            "preview_expires_at",
        )
    ):
        return None
    return CampaignDraftPreviewMetadata(
        content_hash=row["preview_content_hash"],
        revision=row["preview_revision"],
        token_digest=row["preview_token_digest"],
        created_at=row["preview_created_at"],
        expires_at=row["preview_expires_at"],
    )


def store_campaign_draft_preview(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    revision: int,
    *,
    content_hash: str,
    token_digest: str,
    created_at: datetime,
    expires_at: datetime,
    connection=None,
) -> CampaignDraftPreviewMetadata:
    def update(active_connection):
        return active_connection.execute(
            """
            UPDATE campaign_generation_drafts
            SET preview_content_hash = %s, preview_revision = %s,
                preview_token_digest = %s, preview_created_at = %s,
                preview_expires_at = %s
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND revision = %s
              AND status IN ('generated', 'reviewed')
            RETURNING preview_content_hash, preview_revision,
                      preview_token_digest, preview_created_at,
                      preview_expires_at
            """,
            (
                content_hash,
                revision,
                token_digest,
                created_at,
                expires_at,
                draft_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                revision,
            ),
        ).fetchone()

    if connection is not None:
        row = update(connection)
    else:
        with draft_transaction() as active_connection:
            row = update(active_connection)
    if row is None:
        current = get_campaign_draft(
            scope,
            session_id,
            draft_id,
            connection=connection,
        )
        if current is None:
            raise CampaignDraftNotFound("campaign draft not found")
        raise CampaignDraftStaleRevision("campaign draft revision is stale")
    return CampaignDraftPreviewMetadata(
        content_hash=row["preview_content_hash"],
        revision=row["preview_revision"],
        token_digest=row["preview_token_digest"],
        created_at=row["preview_created_at"],
        expires_at=row["preview_expires_at"],
    )


def get_pending_campaign_draft_options(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    revision: int,
    *,
    connection=None,
) -> PersistedCampaignDraftOptionSet | None:
    def read(active_connection):
        active_connection.execute(
            """
            UPDATE campaign_generation_draft_options
            SET status = 'expired'
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND draft_id = %s AND status = 'pending'
              AND expires_at <= CURRENT_TIMESTAMP
            """,
            (scope.tenant_id, scope.fa_id, session_id, draft_id),
        )
        return active_connection.execute(
            """
            SELECT option_set_id, draft_id, base_revision, field_name, options,
                   status, expires_at
            FROM campaign_generation_draft_options
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND draft_id = %s AND base_revision = %s
              AND status = 'pending' AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (scope.tenant_id, scope.fa_id, session_id, draft_id, revision),
        ).fetchone()

    if connection is not None:
        row = read(connection)
    else:
        with draft_transaction() as active_connection:
            row = read(active_connection)
    return _option_from_row(row) if row else None


def create_campaign_draft_option_set(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    proposal: CampaignDraftOptionProposal,
    *,
    connection=None,
) -> PersistedCampaignDraftOptionSet:
    option_set_id = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    def create(active_connection):
        current = active_connection.execute(
            """
            SELECT revision
            FROM campaign_generation_drafts
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND status IN ('generated', 'reviewed')
            FOR UPDATE
            """,
            (draft_id, scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()
        if current is None:
            raise CampaignDraftNotFound("campaign draft not found")
        if current["revision"] != proposal.baseRevision:
            raise CampaignDraftStaleRevision("campaign draft revision is stale")
        active_connection.execute(
            """
            UPDATE campaign_generation_draft_options
            SET status = 'stale'
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND draft_id = %s AND status = 'pending'
            """,
            (scope.tenant_id, scope.fa_id, session_id, draft_id),
        )
        return active_connection.execute(
            """
            INSERT INTO campaign_generation_draft_options
                (option_set_id, tenant_id, fa_id, session_id, draft_id,
                 base_revision, field_name, options, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING option_set_id, draft_id, base_revision, field_name,
                      options, status, expires_at
            """,
            (
                option_set_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                draft_id,
                proposal.baseRevision,
                proposal.field,
                Jsonb(proposal.options),
                expires_at,
            ),
        ).fetchone()

    if connection is not None:
        row = create(connection)
    else:
        with draft_transaction() as active_connection:
            row = create(active_connection)
    return _option_from_row(row)


def mark_campaign_draft_option_selected(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    revision: int,
    option_set_id: str,
    option_number: int,
    *,
    connection=None,
) -> None:
    if not 1 <= option_number <= 10:
        raise CampaignDraftStaleRevision("campaign draft option is unavailable")

    def update(active_connection):
        row = active_connection.execute(
            """
            UPDATE campaign_generation_draft_options
            SET status = 'selected', selected_index = %s
            WHERE option_set_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND draft_id = %s AND base_revision = %s
              AND status = 'pending' AND expires_at > CURRENT_TIMESTAMP
              AND %s <= jsonb_array_length(options)
            RETURNING option_set_id
            """,
            (
                option_number,
                option_set_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                draft_id,
                revision,
                option_number,
            ),
        ).fetchone()
        if row is None:
            raise CampaignDraftStaleRevision("campaign draft option is stale or unavailable")

    if connection is not None:
        update(connection)
    else:
        with draft_transaction() as active_connection:
            update(active_connection)


def create_campaign_draft(
    scope: RequestScope,
    session_id: str,
    artifact: CampaignDraftArtifact,
    creation: CampaignDraftCreationMetadata,
    *,
    connection=None,
) -> PersistedCampaignDraftArtifact:
    creation.require_complete()
    draft_id = str(uuid4())
    model_version = getattr(config.get_settings(), "llm_model", None)

    def create(active_connection):
        row = active_connection.execute(
            f"""
            INSERT INTO campaign_generation_drafts
                (draft_id, tenant_id, fa_id, session_id, objective,
                 references_used, draft, creation_metadata, validation, revision, status,
                 changed_fields, model_version, prompt_version)
            SELECT %s, %s, %s, sessions.session_id, %s, %s, %s, %s, %s,
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
                Jsonb(creation.model_dump(mode="json")),
                Jsonb(artifact.validation.model_dump(mode="json")),
                model_version,
                session_id,
                scope.fa_id,
            ),
        ).fetchone()
        if row is not None:
            active_connection.execute(
                """
                UPDATE campaign_chat_sessions
                SET active_campaign_draft_id = %s
                WHERE session_id = %s AND fa_id = %s
                """,
                (draft_id, session_id, scope.fa_id),
            )
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
    status: str = "generated",
    creation: CampaignDraftCreationMetadata | None = None,
    connection=None,
) -> PersistedCampaignDraftArtifact:
    if artifact.previousRevision != expected_revision:
        raise CampaignDraftStaleRevision("campaign draft revision is stale")
    if artifact.revision != expected_revision + 1:
        raise CampaignDraftStaleRevision("campaign draft revision must advance once")
    if status not in {"generated", "reviewed"}:
        raise ValueError("campaign draft revision status is invalid")

    def update(active_connection):
        row = active_connection.execute(
            f"""
            UPDATE campaign_generation_drafts
            SET objective = %s, references_used = %s, draft = %s,
                creation_metadata = COALESCE(%s, creation_metadata),
                validation = %s, revision = %s, status = %s,
                changed_fields = %s, updated_at = CURRENT_TIMESTAMP,
                preview_content_hash = NULL, preview_revision = NULL,
                preview_token_digest = NULL, preview_created_at = NULL,
                preview_expires_at = NULL
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND revision = %s
              AND status IN ('generated', 'reviewed')
            RETURNING {_RETURNING}
            """,
            (
                artifact.objective,
                Jsonb([item.model_dump(mode="json") for item in artifact.referencesUsed]),
                Jsonb(artifact.draft.model_dump(mode="json")),
                Jsonb(creation.model_dump(mode="json")) if creation else None,
                Jsonb(artifact.validation.model_dump(mode="json")),
                artifact.revision,
                status,
                list(artifact.changedFields),
                draft_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                expected_revision,
            ),
        ).fetchone()
        if row is not None:
            active_connection.execute(
                """
                UPDATE campaign_generation_draft_options
                SET status = 'stale'
                WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
                  AND draft_id = %s AND status = 'pending'
                """,
                (scope.tenant_id, scope.fa_id, session_id, draft_id),
            )
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


def update_campaign_draft_creation_metadata(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    expected_revision: int,
    creation: CampaignDraftCreationMetadata,
    *,
    connection=None,
) -> PersistedCampaignDraftArtifact:
    """Persist adviser-owned creation fields without invoking the model."""

    def update(active_connection):
        row = active_connection.execute(
            f"""
            UPDATE campaign_generation_drafts
            SET creation_metadata = %s, revision = %s, status = 'reviewed',
                changed_fields = ARRAY[]::TEXT[], updated_at = CURRENT_TIMESTAMP,
                preview_content_hash = NULL, preview_revision = NULL,
                preview_token_digest = NULL, preview_created_at = NULL,
                preview_expires_at = NULL
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND revision = %s
              AND status IN ('generated', 'reviewed')
            RETURNING {_RETURNING}
            """,
            (
                Jsonb(creation.model_dump(mode="json")),
                expected_revision + 1,
                draft_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                expected_revision,
            ),
        ).fetchone()
        if row is not None:
            active_connection.execute(
                """
                UPDATE campaign_generation_draft_options
                SET status = 'stale'
                WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
                  AND draft_id = %s AND status = 'pending'
                """,
                (scope.tenant_id, scope.fa_id, session_id, draft_id),
            )
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


def confirm_campaign_draft(
    scope: RequestScope,
    session_id: str,
    draft_id: str,
    revision: int,
    confirmation_token: str,
    idempotency_key: str,
    *,
    now: datetime | None = None,
) -> CampaignDraftConfirmationResult:
    """Atomically create one official campaign row and confirm its source draft."""
    from app.campaigns.preview import (
        campaign_preview_content_hash,
        campaign_preview_token_digest,
        get_campaign_preview_signer,
        revalidate_campaign_draft_preview,
    )

    confirmed_at = now or datetime.now(timezone.utc)
    with draft_transaction() as connection:
        row = connection.execute(
            f"""
            SELECT {_RETURNING}, preview_content_hash, preview_revision,
                   preview_token_digest, preview_created_at, preview_expires_at,
                   created_campaign_id, confirmed_revision, confirmed_at,
                   confirmation_idempotency_key
            FROM campaign_generation_drafts
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s
            FOR UPDATE
            """,
            (draft_id, scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()
        if row is None:
            raise CampaignDraftNotFound("campaign draft not found")
        if row["status"] == "confirmed":
            if (
                row["confirmation_idempotency_key"] == idempotency_key
                and row["created_campaign_id"] is not None
            ):
                return CampaignDraftConfirmationResult(
                    campaign_id=str(row["created_campaign_id"]),
                    created=False,
                )
            raise CampaignDraftConfirmationConflict(
                "campaign draft has already been confirmed"
            )
        if row["status"] not in {"generated", "reviewed"}:
            raise CampaignDraftConfirmationConflict(
                "campaign draft is not available for confirmation"
            )
        if row["revision"] != revision:
            raise CampaignDraftStaleRevision("campaign draft revision is stale")

        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{scope.tenant_id}:{scope.fa_id}:{idempotency_key}",),
        )
        reused_key = connection.execute(
            """
            SELECT draft_id
            FROM campaign_generation_drafts
            WHERE tenant_id = %s AND fa_id = %s
              AND confirmation_idempotency_key = %s AND draft_id <> %s
            """,
            (scope.tenant_id, scope.fa_id, idempotency_key, draft_id),
        ).fetchone()
        if reused_key is not None:
            raise CampaignDraftConfirmationConflict(
                "confirmation idempotency key has already been used"
            )

        artifact = _from_row(row)
        try:
            artifact.creation.require_complete()
        except ValueError as exc:
            raise CampaignDraftConfirmationConflict(str(exc)) from exc
        validation = revalidate_campaign_draft_preview(artifact, scope)
        content_hash = campaign_preview_content_hash(
            artifact.draft,
            validation,
            artifact.creation,
        )
        required_metadata = (
            "preview_content_hash",
            "preview_revision",
            "preview_token_digest",
            "preview_created_at",
            "preview_expires_at",
        )
        if any(row[field] is None for field in required_metadata):
            raise CampaignDraftConfirmationConflict(
                "A fresh server preview is required before confirmation"
            )
        if row["preview_expires_at"] <= confirmed_at:
            from app.campaigns.preview import CampaignPreviewTokenError

            raise CampaignPreviewTokenError(
                "expired_confirmation_token",
                "Campaign draft preview token has expired",
            )
        if (
            row["preview_revision"] != revision
            or row["preview_content_hash"] != content_hash
            or not hmac.compare_digest(
                row["preview_token_digest"],
                campaign_preview_token_digest(confirmation_token),
            )
        ):
            raise CampaignDraftConfirmationConflict(
                "Campaign draft preview is stale or has been superseded"
            )
        claims = get_campaign_preview_signer().verify(
            confirmation_token,
            draft_id=draft_id,
            revision=revision,
            content_hash=content_hash,
            scope=scope,
            session_id=session_id,
            now=confirmed_at,
        )
        if int(row["preview_expires_at"].timestamp()) != claims.expires_at:
            raise CampaignDraftConfirmationConflict(
                "Campaign draft preview is stale or has been superseded"
            )

        try:
            tenant_id = str(UUID(_storage_tenant_id(scope)))
            creator_id = str(UUID(scope.fa_id))
        except ValueError as exc:
            raise CampaignDraftConfirmationConflict(
                "campaign creation requires UUID-based adviser and tenant context"
            ) from exc

        campaign_id = uuid4()
        campaign_code = f"PULSE-{campaign_id.hex[:12].upper()}"
        connection.execute(
            """
            INSERT INTO campaign (
                tenant_id, campaign_id, campaign_code, name, description,
                status, start_date, end_date, origin, audience_source,
                client_messaging, audience_criteria, created_by_user_id
            ) VALUES (
                %s, %s, %s, %s, %s,
                'draft', %s, %s, 'advisor', %s,
                %s, %s, %s
            )
            """,
            (
                tenant_id,
                campaign_id,
                campaign_code,
                artifact.draft.name,
                artifact.draft.description,
                artifact.creation.startDate,
                artifact.creation.endDate,
                artifact.creation.audienceSource,
                artifact.draft.clientMessage,
                Jsonb(criteria_to_storage(
                    artifact.draft.criteria.model_dump(mode="json")
                )),
                creator_id,
            ),
        )
        updated = connection.execute(
            """
            UPDATE campaign_generation_drafts
            SET status = 'confirmed', created_campaign_id = %s,
                confirmed_revision = %s, confirmed_at = %s,
                confirmation_idempotency_key = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE draft_id = %s AND tenant_id = %s AND fa_id = %s
              AND session_id = %s AND revision = %s
              AND status IN ('generated', 'reviewed')
            RETURNING draft_id
            """,
            (
                campaign_id,
                revision,
                confirmed_at,
                idempotency_key,
                draft_id,
                scope.tenant_id,
                scope.fa_id,
                session_id,
                revision,
            ),
        ).fetchone()
        if updated is None:
            raise CampaignDraftStaleRevision("campaign draft revision is stale")
        connection.execute(
            """
            UPDATE campaign_chat_sessions
            SET active_campaign_draft_id = NULL
            WHERE session_id = %s AND fa_id = %s
              AND active_campaign_draft_id = %s
            """,
            (session_id, scope.fa_id, draft_id),
        )
        return CampaignDraftConfirmationResult(
            campaign_id=str(campaign_id),
            created=True,
        )

"""Server-verified Stage 9 preview tokens for review-only campaign drafts."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import hmac
import json
import secrets
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.campaigns.models import (
    CampaignDraft,
    CampaignDraftCreationMetadata,
    CampaignDraftValidation,
    PersistedCampaignDraftArtifact,
)
from app.campaigns.reference_repository import (
    CampaignReferenceRepository,
    CatalogueConfigurationError,
    RetrievalTokenError,
    get_reference_repository,
)
from app.campaigns.repository import RequestScope
from app.campaigns.validation import validate_campaign_draft_policy

PREVIEW_TOKEN_TTL = timedelta(minutes=5)
PREVIEW_TOKEN_VERSION = 1
_PROCESS_PREVIEW_SECRET = secrets.token_bytes(32)


class CampaignPreviewConfigurationError(RuntimeError):
    """Safe preview configuration failure without secret details."""


class CampaignPreviewTokenError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CampaignPreviewTokenClaims:
    draft_id: str
    revision: int
    content_hash: str
    tenant_id: str
    fa_id: str
    session_id: str
    issued_at: int
    expires_at: int
    nonce: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def campaign_preview_content_hash(
    draft: CampaignDraft,
    validation: CampaignDraftValidation,
    creation: CampaignDraftCreationMetadata,
) -> str:
    """Hash the exact content and policy result displayed in the final preview."""
    canonical = json.dumps(
        {
            "draft": draft.model_dump(mode="json"),
            "creation": creation.model_dump(mode="json"),
            "validation": validation.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def campaign_preview_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CampaignPreviewTokenSigner:
    def __init__(
        self,
        secret: bytes,
        ttl: timedelta = PREVIEW_TOKEN_TTL,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("preview token secret must be at least 16 bytes")
        if ttl <= timedelta(0):
            raise ValueError("preview token TTL must be positive")
        self._secret = secret
        self._ttl = ttl

    def issue(
        self,
        *,
        draft_id: str,
        revision: int,
        content_hash: str,
        scope: RequestScope,
        session_id: str,
        now: datetime,
    ) -> tuple[str, CampaignPreviewTokenClaims]:
        issued_at = int(now.astimezone(timezone.utc).timestamp())
        claims = CampaignPreviewTokenClaims(
            draft_id=draft_id,
            revision=revision,
            content_hash=content_hash,
            tenant_id=scope.tenant_id,
            fa_id=scope.fa_id,
            session_id=session_id,
            issued_at=issued_at,
            expires_at=int((now + self._ttl).astimezone(timezone.utc).timestamp()),
            nonce=secrets.token_urlsafe(12),
        )
        payload = {
            "v": PREVIEW_TOKEN_VERSION,
            "draft_id": claims.draft_id,
            "revision": claims.revision,
            "content_sha256": claims.content_hash,
            "tenant_id": claims.tenant_id,
            "fa_id": claims.fa_id,
            "session_id": claims.session_id,
            "iat": claims.issued_at,
            "exp": claims.expires_at,
            "nonce": claims.nonce,
        }
        encoded = _encode_part(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        signature = _encode_part(
            hmac.new(
                self._secret,
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
        )
        return f"{encoded}.{signature}", claims

    def verify(
        self,
        token: str,
        *,
        draft_id: str,
        revision: int,
        content_hash: str,
        scope: RequestScope,
        session_id: str,
        now: datetime,
    ) -> CampaignPreviewTokenClaims:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = _encode_part(
                hmac.new(
                    self._secret,
                    encoded.encode("ascii"),
                    hashlib.sha256,
                ).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise CampaignPreviewTokenError(
                    "invalid_confirmation_token",
                    "Campaign draft preview token is invalid",
                )
            payload = json.loads(_decode_part(encoded))
            claims = CampaignPreviewTokenClaims(
                draft_id=payload["draft_id"],
                revision=payload["revision"],
                content_hash=payload["content_sha256"],
                tenant_id=payload["tenant_id"],
                fa_id=payload["fa_id"],
                session_id=payload["session_id"],
                issued_at=payload["iat"],
                expires_at=payload["exp"],
                nonce=payload["nonce"],
            )
        except CampaignPreviewTokenError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise CampaignPreviewTokenError(
                "invalid_confirmation_token",
                "Campaign draft preview token is invalid",
            ) from exc

        if (
            type(payload.get("v")) is not int
            or payload.get("v") != PREVIEW_TOKEN_VERSION
            or not isinstance(claims.draft_id, str)
            or type(claims.revision) is not int
            or not isinstance(claims.content_hash, str)
            or len(claims.content_hash) != 64
            or not isinstance(claims.tenant_id, str)
            or not isinstance(claims.fa_id, str)
            or not isinstance(claims.session_id, str)
            or type(claims.issued_at) is not int
            or type(claims.expires_at) is not int
            or not isinstance(claims.nonce, str)
            or not claims.nonce
            or claims.issued_at > claims.expires_at
        ):
            raise CampaignPreviewTokenError(
                "invalid_confirmation_token",
                "Campaign draft preview token is invalid",
            )
        if claims.expires_at <= int(now.astimezone(timezone.utc).timestamp()):
            raise CampaignPreviewTokenError(
                "expired_confirmation_token",
                "Campaign draft preview token has expired",
            )
        if (
            claims.draft_id != draft_id
            or claims.revision != revision
            or claims.content_hash != content_hash
            or claims.tenant_id != scope.tenant_id
            or claims.fa_id != scope.fa_id
            or claims.session_id != session_id
        ):
            raise CampaignPreviewTokenError(
                "stale_confirmation_token",
                "Campaign draft preview is stale or does not match this review",
            )
        return claims


def revalidate_campaign_draft_preview(
    artifact: PersistedCampaignDraftArtifact,
    scope: RequestScope,
    repository: CampaignReferenceRepository | None = None,
) -> CampaignDraftValidation:
    """Revalidate current citations and policy immediately before preview."""
    service = repository or get_reference_repository()
    as_of = service.clock().astimezone(ZoneInfo("Asia/Singapore")).date()
    available = {
        (entry.referenceId, entry.version): entry
        for entry in service.catalogue.entries
        if scope.tenant_id in entry.tenantIds
        and entry.approvalStatus == "approved"
        and entry.validFrom <= as_of
        and (entry.validUntil is None or entry.validUntil >= as_of)
    }
    citations = [
        (citation.referenceId, citation.version)
        for citation in artifact.referencesUsed
    ]
    try:
        references = [available[citation] for citation in citations]
    except KeyError as exc:
        raise RetrievalTokenError(
            "invalid_reference_citation",
            "A cited campaign reference is unavailable for preview",
        ) from exc
    return validate_campaign_draft_policy(
        artifact.objective,
        artifact.draft,
        references,
    )


@lru_cache
def get_campaign_preview_signer() -> CampaignPreviewTokenSigner:
    try:
        configured = get_settings().campaign_preview_secret
        secret = (
            configured.get_secret_value().encode("utf-8")
            if configured is not None
            else _PROCESS_PREVIEW_SECRET
        )
        return CampaignPreviewTokenSigner(secret)
    except ValueError as exc:
        raise CampaignPreviewConfigurationError(
            "Campaign draft preview is unavailable"
        ) from exc

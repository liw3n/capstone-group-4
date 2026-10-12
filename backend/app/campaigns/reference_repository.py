"""Deterministic, scoped retrieval from the synthetic campaign catalogue."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
from typing import Callable
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.campaigns.models import (
    CampaignReference,
    CampaignReferenceCatalogue,
    CampaignReferenceQuery,
    CampaignReferenceResult,
    CampaignReferenceResultItem,
)
from app.campaigns.repository import RequestScope

CATALOGUE_PATH = Path(__file__).with_name("catalogue.json")
TOKEN_TTL = timedelta(minutes=5)
TOKEN_VERSION = 1
MIN_RELEVANCE_SCORE = 6
_TOKEN_SECRET_ENV = "PULSE_CAMPAIGN_RETRIEVAL_SECRET"
_DEFAULT_TOKEN_SECRET = os.environ.get(_TOKEN_SECRET_ENV)
_PROCESS_TOKEN_SECRET = (
    _DEFAULT_TOKEN_SECRET.encode("utf-8") if _DEFAULT_TOKEN_SECRET else secrets.token_bytes(32)
)
_TERM_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "business",
    "by", "campaign", "client", "clients", "create", "for", "from", "help", "high",
    "i", "in", "is", "it", "me", "my", "objective", "of", "on", "our", "people",
    "plan", "planning", "proposal", "review", "run", "that", "the", "their", "them",
    "this", "to", "us", "want", "who", "with",
}


class CatalogueConfigurationError(RuntimeError):
    """Safe catalogue configuration failure without file or parser details."""


class RetrievalTokenError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RetrievalTokenClaims:
    objective_hash: str
    tenant_id: str
    fa_id: str
    catalogue_version: int
    references: tuple[tuple[str, int], ...]
    issued_at: int
    expires_at: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_objective(objective: str) -> str:
    return re.sub(r"\s+", " ", objective.strip()).casefold()


def _objective_hash(objective: str) -> str:
    return hashlib.sha256(_normalize_objective(objective).encode("utf-8")).hexdigest()


def _terms(value: str) -> set[str]:
    return {term for term in _TERM_PATTERN.findall(value.casefold()) if term not in _STOP_WORDS}


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class RetrievalTokenSigner:
    def __init__(self, secret: bytes, ttl: timedelta = TOKEN_TTL) -> None:
        if len(secret) < 16:
            raise ValueError("retrieval token secret must be at least 16 bytes")
        if ttl <= timedelta(0):
            raise ValueError("retrieval token TTL must be positive")
        self._secret = secret
        self._ttl = ttl

    def issue(
        self,
        objective: str,
        scope: RequestScope,
        catalogue_version: int,
        references: list[CampaignReferenceResultItem],
        now: datetime,
    ) -> str:
        issued_at = int(now.timestamp())
        payload = {
            "v": TOKEN_VERSION,
            "objective_sha256": _objective_hash(objective),
            "tenant_id": scope.tenant_id,
            "fa_id": scope.fa_id,
            "catalogue_version": catalogue_version,
            "references": [
                {"reference_id": item.referenceId, "version": item.version}
                for item in references
            ],
            "iat": issued_at,
            "exp": int((now + self._ttl).timestamp()),
        }
        encoded = _encode_part(json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))
        signature = _encode_part(hmac.new(
            self._secret, encoded.encode("ascii"), hashlib.sha256
        ).digest())
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        objective: str,
        scope: RequestScope,
        catalogue_version: int,
        now: datetime,
    ) -> RetrievalTokenClaims:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = _encode_part(hmac.new(
                self._secret, encoded.encode("ascii"), hashlib.sha256
            ).digest())
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise RetrievalTokenError("invalid_retrieval_token", "Retrieval token is invalid")
            payload = json.loads(_decode_part(encoded))
            references = tuple(
                (item["reference_id"], item["version"])
                for item in payload["references"]
            )
            claims = RetrievalTokenClaims(
                objective_hash=payload["objective_sha256"],
                tenant_id=payload["tenant_id"],
                fa_id=payload["fa_id"],
                catalogue_version=payload["catalogue_version"],
                references=references,
                issued_at=payload["iat"],
                expires_at=payload["exp"],
            )
        except RetrievalTokenError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise RetrievalTokenError(
                "invalid_retrieval_token", "Retrieval token is invalid"
            ) from exc

        if type(payload.get("v")) is not int or payload.get("v") != TOKEN_VERSION:
            raise RetrievalTokenError("invalid_retrieval_token", "Retrieval token is invalid")
        if (not isinstance(claims.objective_hash, str)
                or not isinstance(claims.tenant_id, str)
                or not isinstance(claims.fa_id, str)
                or type(claims.catalogue_version) is not int
                or type(claims.issued_at) is not int
                or type(claims.expires_at) is not int
                or claims.issued_at > claims.expires_at):
            raise RetrievalTokenError("invalid_retrieval_token", "Retrieval token is invalid")
        if claims.expires_at <= int(now.timestamp()):
            raise RetrievalTokenError("expired_retrieval_token", "Retrieval token has expired")
        if claims.objective_hash != _objective_hash(objective):
            raise RetrievalTokenError(
                "invalid_retrieval_token", "Retrieval token does not match the objective"
            )
        if claims.tenant_id != scope.tenant_id or claims.fa_id != scope.fa_id:
            raise RetrievalTokenError(
                "scope_mismatch", "Retrieval token is not valid for this adviser context"
            )
        if claims.catalogue_version != catalogue_version:
            raise RetrievalTokenError(
                "invalid_retrieval_token", "Retrieval token catalogue version is stale"
            )
        if any(
            not isinstance(reference_id, str) or type(version) is not int or version < 1
            for reference_id, version in claims.references
        ):
            raise RetrievalTokenError("invalid_retrieval_token", "Retrieval token is invalid")
        return claims


def load_catalogue(path: Path = CATALOGUE_PATH) -> CampaignReferenceCatalogue:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return CampaignReferenceCatalogue.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CatalogueConfigurationError("Campaign reference catalogue is unavailable") from exc


def _score_reference(
    entry: CampaignReference,
    objective_terms: set[str],
    category_was_explicit: bool,
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    matched_tags: list[str] = []

    if category_was_explicit:
        score += 10
        reasons.append("category_filter")
    if entry.category in objective_terms:
        score += 6
        reasons.append("category_term")

    tag_score = 0
    for tag in entry.objectiveTags:
        tag_terms = _terms(tag)
        overlap = tag_terms & objective_terms
        if overlap:
            matched_tags.append(tag)
            tag_score += 3 * len(overlap)
            if tag_terms <= objective_terms:
                tag_score += 4
    if matched_tags:
        score += min(tag_score, 24)
        reasons.append("objective_tag")

    title_overlap = len(_terms(entry.title) & objective_terms)
    pattern_overlap = len(
        (_terms(entry.descriptionPattern) | _terms(entry.messagingPattern)) & objective_terms
    )
    lexical_score = min(title_overlap * 2, 6) + min(pattern_overlap, 4)
    if lexical_score:
        score += lexical_score
        reasons.append("lexical_overlap")
    return score, matched_tags, reasons


class CampaignReferenceRepository:
    def __init__(
        self,
        catalogue: CampaignReferenceCatalogue,
        signer: RetrievalTokenSigner,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.catalogue = catalogue
        self.signer = signer
        self.clock = clock

    def find(
        self, query: CampaignReferenceQuery, scope: RequestScope
    ) -> CampaignReferenceResult:
        now = self.clock().astimezone(timezone.utc)
        as_of = now.astimezone(ZoneInfo("Asia/Singapore")).date()
        objective_terms = _terms(query.objective)
        explicit_categories = set(query.categories or [])
        scored: list[tuple[int, CampaignReference, list[str], list[str]]] = []

        # Scope, governance state and validity are enforced before scoring.
        for entry in self.catalogue.entries:
            if scope.tenant_id not in entry.tenantIds:
                continue
            if entry.approvalStatus != "approved":
                continue
            if entry.validFrom > as_of or (
                entry.validUntil is not None and entry.validUntil < as_of
            ):
                continue
            if explicit_categories and entry.category not in explicit_categories:
                continue
            score, matched_tags, reasons = _score_reference(
                entry, objective_terms, entry.category in explicit_categories
            )
            if score >= MIN_RELEVANCE_SCORE:
                scored.append((score, entry, matched_tags, reasons))

        scored.sort(key=lambda item: (-item[0], item[1].referenceId, -item[1].version))
        selected = scored[:query.limit]
        references = [
            CampaignReferenceResultItem(
                referenceId=entry.referenceId,
                version=entry.version,
                title=entry.title,
                category=entry.category,
                matchedTags=matched_tags,
                matchReasons=reasons,
                descriptionPattern=entry.descriptionPattern,
                messagingPattern=entry.messagingPattern,
                typicalCriteria=entry.typicalCriteria,
                targetingRationale=entry.targetingRationale,
                requiredDisclaimers=entry.requiredDisclaimers,
            )
            for _, entry, matched_tags, reasons in selected
        ]
        token = self.signer.issue(
            query.objective, scope, self.catalogue.catalogueVersion, references, now
        )
        return CampaignReferenceResult(
            query=query.objective,
            catalogueVersion=self.catalogue.catalogueVersion,
            retrievalToken=token,
            references=references,
            returnedCount=len(references),
            truncated=len(scored) > query.limit,
        )

    def verify_token(
        self, token: str, objective: str, scope: RequestScope
    ) -> RetrievalTokenClaims:
        return self.signer.verify(
            token, objective, scope, self.catalogue.catalogueVersion,
            self.clock().astimezone(timezone.utc),
        )


@lru_cache
def get_reference_repository() -> CampaignReferenceRepository:
    try:
        signer = RetrievalTokenSigner(_PROCESS_TOKEN_SECRET)
    except ValueError as exc:
        raise CatalogueConfigurationError(
            "Campaign reference catalogue is unavailable"
        ) from exc
    return CampaignReferenceRepository(load_catalogue(), signer)

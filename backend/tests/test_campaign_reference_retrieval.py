from datetime import datetime, timedelta, timezone

import pytest

from app.campaigns.models import CampaignReferenceCatalogue, CampaignReferenceQuery
from app.campaigns.reference_repository import (
    CampaignReferenceRepository,
    RetrievalTokenError,
    RetrievalTokenSigner,
    load_catalogue,
)
from app.campaigns.repository import DEMO_FA, RequestScope

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
SECRET = b"test-retrieval-secret-at-least-32-bytes"


def repository(catalogue=None, now=NOW, ttl=timedelta(minutes=5)):
    return CampaignReferenceRepository(
        catalogue or load_catalogue(), RetrievalTokenSigner(SECRET, ttl), lambda: now
    )


def test_retrieval_is_deterministic_bounded_and_reports_truncation():
    service = repository()
    query = CampaignReferenceQuery(
        objective=("Retirement protection education property legacy income resilience "
                   "funding mortgage beneficiary healthcare savings readiness"),
        limit=3,
    )
    first = service.find(query, RequestScope(DEMO_FA))
    second = service.find(query, RequestScope(DEMO_FA))
    assert first == second
    assert first.returnedCount == 3
    assert first.truncated is True
    assert [item.referenceId for item in first.references] == [
        item.referenceId for item in second.references
    ]


def test_scope_approval_and_validity_filter_before_ranking():
    source = load_catalogue().entries[0]
    entries = [
        source,
        source.model_copy(update={"referenceId": "campaign-pattern-retired-001",
                                  "approvalStatus": "retired"}),
        source.model_copy(update={"referenceId": "campaign-pattern-expired-001",
                                  "validUntil": NOW.date() - timedelta(days=1)}),
        source.model_copy(update={"referenceId": "campaign-pattern-future-001",
                                  "validFrom": NOW.date() + timedelta(days=1)}),
        source.model_copy(update={"referenceId": "campaign-pattern-other-tenant-001",
                                  "tenantIds": ["other-tenant"]}),
    ]
    catalogue = CampaignReferenceCatalogue(catalogueVersion=7, entries=entries)
    result = repository(catalogue).find(
        CampaignReferenceQuery(objective="Retirement income readiness for older clients"),
        RequestScope(DEMO_FA),
    )
    assert [item.referenceId for item in result.references] == [source.referenceId]


def test_equal_scores_use_stable_reference_id_then_version_order():
    source = load_catalogue().entries[0]
    later_id = source.model_copy(update={"referenceId": "campaign-pattern-zeta-001"})
    earlier_id = source.model_copy(update={"referenceId": "campaign-pattern-alpha-001",
                                           "version": 2})
    catalogue = CampaignReferenceCatalogue(
        catalogueVersion=8, entries=[later_id, earlier_id]
    )
    result = repository(catalogue).find(
        CampaignReferenceQuery(objective="Retirement income readiness review"),
        RequestScope(DEMO_FA),
    )
    assert [(item.referenceId, item.version) for item in result.references] == [
        ("campaign-pattern-alpha-001", 2), ("campaign-pattern-zeta-001", 1)
    ]


def test_irrelevant_objective_returns_empty_success_with_valid_token():
    service = repository()
    scope = RequestScope(DEMO_FA)
    objective = "Organise a charity fun run for employees next quarter"
    result = service.find(CampaignReferenceQuery(objective=objective), scope)
    assert result.references == []
    assert result.returnedCount == 0
    assert result.truncated is False
    claims = service.verify_token(result.retrievalToken, objective, scope)
    assert claims.references == ()


def test_token_rejects_tampering_expiry_objective_and_cross_scope():
    scope = RequestScope(DEMO_FA)
    objective = "Review retirement income readiness before leaving work"
    service = repository(ttl=timedelta(seconds=1))
    result = service.find(CampaignReferenceQuery(objective=objective), scope)

    with pytest.raises(RetrievalTokenError, match="invalid") as altered:
        service.verify_token(result.retrievalToken[:-1] + "x", objective, scope)
    assert altered.value.code == "invalid_retrieval_token"

    with pytest.raises(RetrievalTokenError) as wrong_objective:
        service.verify_token(result.retrievalToken, objective + " changed", scope)
    assert wrong_objective.value.code == "invalid_retrieval_token"

    with pytest.raises(RetrievalTokenError) as cross_scope:
        service.verify_token(result.retrievalToken, objective, RequestScope("adv-other"))
    assert cross_scope.value.code == "scope_mismatch"

    expired_service = repository(now=NOW + timedelta(seconds=2), ttl=timedelta(seconds=1))
    with pytest.raises(RetrievalTokenError) as expired:
        expired_service.signer.verify(
            result.retrievalToken, objective, scope,
            expired_service.catalogue.catalogueVersion, NOW + timedelta(seconds=2),
        )
    assert expired.value.code == "expired_retrieval_token"

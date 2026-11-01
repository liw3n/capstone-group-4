from datetime import datetime, timedelta, timezone

import pytest

from app.campaigns.preview import (
    CampaignPreviewTokenError,
    CampaignPreviewTokenSigner,
    campaign_preview_content_hash,
    campaign_preview_token_digest,
    revalidate_campaign_draft_preview,
)
from app.campaigns.models import CampaignReferenceCatalogue
from app.campaigns.reference_repository import (
    CampaignReferenceRepository,
    RetrievalTokenError,
    RetrievalTokenSigner,
    load_catalogue,
)
from app.campaigns.repository import RequestScope
from test_orchestrator import persisted_campaign_draft


NOW = datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)
SCOPE = RequestScope("advisor-123", "tenant-123")


def test_preview_hash_is_canonical_and_changes_with_visible_content():
    artifact = persisted_campaign_draft()
    first = campaign_preview_content_hash(
        artifact.draft, artifact.validation, artifact.creation
    )
    equivalent = artifact.draft.__class__.model_validate(
        artifact.draft.model_dump(mode="json")
    )
    assert campaign_preview_content_hash(
        equivalent, artifact.validation, artifact.creation
    ) == first
    changed = artifact.draft.model_copy(update={"name": "Different review name"})
    assert campaign_preview_content_hash(
        changed, artifact.validation, artifact.creation
    ) != first
    changed_creation = artifact.creation.model_copy(
        update={"endDate": artifact.creation.startDate}
    )
    assert campaign_preview_content_hash(
        artifact.draft, artifact.validation, changed_creation
    ) != first


def test_preview_token_is_scope_revision_content_and_expiry_bound():
    signer = CampaignPreviewTokenSigner(b"preview-test-secret-value", timedelta(minutes=5))
    content_hash = "a" * 64
    token, issued = signer.issue(
        draft_id="11111111-1111-4111-8111-111111111111",
        revision=3,
        content_hash=content_hash,
        scope=SCOPE,
        session_id="session-123",
        now=NOW,
    )
    claims = signer.verify(
        token,
        draft_id=issued.draft_id,
        revision=3,
        content_hash=content_hash,
        scope=SCOPE,
        session_id="session-123",
        now=NOW + timedelta(minutes=1),
    )
    assert claims == issued
    assert len(campaign_preview_token_digest(token)) == 64

    checks = (
        {"token": token[:-1] + "x"},
        {"revision": 4},
        {"content_hash": "b" * 64},
        {"scope": RequestScope("other-advisor", "tenant-123")},
        {"session_id": "other-session"},
    )
    defaults = {
        "token": token,
        "draft_id": issued.draft_id,
        "revision": 3,
        "content_hash": content_hash,
        "scope": SCOPE,
        "session_id": "session-123",
        "now": NOW + timedelta(minutes=1),
    }
    for change in checks:
        with pytest.raises(CampaignPreviewTokenError):
            signer.verify(**(defaults | change))

    with pytest.raises(CampaignPreviewTokenError) as expired:
        signer.verify(**(defaults | {"now": NOW + timedelta(minutes=5)}))
    assert expired.value.code == "expired_confirmation_token"


def test_preview_revalidates_current_catalogue_citations_and_policy():
    artifact = persisted_campaign_draft()
    service = CampaignReferenceRepository(
        load_catalogue(),
        RetrievalTokenSigner(b"preview-retrieval-test-secret-value"),
        lambda: NOW,
    )

    validation = revalidate_campaign_draft_preview(
        artifact, RequestScope("advisor-123"), service
    )

    assert validation.schema_valid is True
    assert validation.policy_valid is True


def test_preview_rejects_citation_that_is_no_longer_approved():
    artifact = persisted_campaign_draft()
    catalogue = load_catalogue()
    entries = [
        entry.model_copy(update={"approvalStatus": "retired"})
        if entry.referenceId == artifact.referencesUsed[0].referenceId
        else entry
        for entry in catalogue.entries
    ]
    service = CampaignReferenceRepository(
        CampaignReferenceCatalogue(
            catalogueVersion=catalogue.catalogueVersion + 1,
            entries=entries,
        ),
        RetrievalTokenSigner(b"preview-retrieval-test-secret-value"),
        lambda: NOW,
    )

    with pytest.raises(RetrievalTokenError) as unavailable:
        revalidate_campaign_draft_preview(
            artifact, RequestScope("advisor-123"), service
        )

    assert unavailable.value.code == "invalid_reference_citation"

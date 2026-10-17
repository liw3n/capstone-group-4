from datetime import date

import pytest
from pydantic import ValidationError

from app.campaigns.models import (
    CampaignDraft,
    CampaignDraftChanges,
    CampaignDraftConfirmationRequest,
    CampaignDraftCriteria,
    CampaignDraftPreviewRequest,
    CampaignReference,
    CampaignReferenceQuery,
    PrepareCampaignDraftArguments,
    ReviseCampaignDraftArguments,
)


def valid_draft() -> dict:
    return {
        "name": "Synthetic retirement readiness review",
        "description": "Invite clients to review retirement assumptions.",
        "clientMessage": "Would you like an educational retirement review?",
        "criteria": {"ageGroups": ["55to64"], "genders": [], "cashBands": []},
        "targetDemographicSummary": "Clients nearing retirement, subject to review.",
        "rationale": {
            "ageGroups": "The objective concerns a retirement transition.",
            "genders": "The objective is not gender-specific.",
            "cashBands": "No cash threshold was stated.",
        },
        "assumptions": ["Retirement timing must be confirmed."],
        "disclaimer": "Educational information only; suitability requires individual review.",
    }


def test_contracts_reject_unknown_fields_and_unsupported_enums():
    with pytest.raises(ValidationError):
        CampaignDraftCriteria.model_validate({
            "ageGroups": ["nearlyRetired"], "genders": [], "cashBands": []
        })
    with pytest.raises(ValidationError):
        CampaignReferenceQuery.model_validate({
            "objective": "Create a retirement education campaign", "limit": 3,
            "tenant_id": "injected",
        })
    with pytest.raises(ValidationError):
        CampaignDraft.model_validate({**valid_draft(), "status": "active"})
    with pytest.raises(ValidationError):
        CampaignDraft.model_validate({
            **valid_draft(),
            "rationale": {"ageGroups": "Only one rationale"},
        })


def test_model_facing_contracts_exclude_server_owned_fields():
    forbidden = {"tenant_id", "tenantId", "fa_id", "faId", "status", "createdBy", "createdAt"}
    for contract in (
        CampaignReferenceQuery, PrepareCampaignDraftArguments,
        ReviseCampaignDraftArguments, CampaignDraftPreviewRequest,
        CampaignDraftConfirmationRequest,
    ):
        properties = set(contract.model_json_schema().get("properties", {}))
        assert not properties & forbidden


def test_reference_contract_validates_dates_and_targeting_rationale():
    base = {
        "referenceId": "campaign-pattern-test-001",
        "title": "Synthetic reference",
        "category": "retirement",
        "objectiveTags": ["retirement-readiness"],
        "descriptionPattern": "A reusable synthetic description.",
        "messagingPattern": "A reusable synthetic message.",
        "typicalCriteria": {"ageGroups": ["55to64"], "genders": [], "cashBands": []},
        "targetingRationale": {
            "ageGroups": "Age rationale.", "genders": "Gender rationale.",
            "cashBands": "Cash rationale.",
        },
        "requiredDisclaimers": ["Educational information only."],
        "prohibitedClaims": ["Guaranteed returns"],
        "approvalStatus": "approved",
        "version": 1,
        "validFrom": date(2026, 1, 1),
        "validUntil": date(2025, 12, 31),
        "tenantIds": ["pulse-demo"],
    }
    with pytest.raises(ValidationError):
        CampaignReference.model_validate(base)


def test_revision_contract_requires_exact_selected_change_fields():
    valid = {
        "objective": "Invite clients to an educational retirement review",
        "referencesUsed": [],
        "currentDraft": valid_draft(),
        "proposedChanges": {"name": "A more distinctive review name"},
        "fields": ["name"],
        "instruction": "Make the name more distinctive",
        "revision": 1,
    }
    parsed = ReviseCampaignDraftArguments.model_validate(valid)
    assert parsed.proposedChanges.name == "A more distinctive review name"

    with pytest.raises(ValidationError):
        ReviseCampaignDraftArguments.model_validate({
            **valid,
            "proposedChanges": {
                "name": "A more distinctive review name",
                "description": "An unselected description change",
            },
        })
    with pytest.raises(ValidationError):
        ReviseCampaignDraftArguments.model_validate({
            **valid,
            "fields": ["name", "name"],
        })
    with pytest.raises(ValidationError):
        CampaignDraftChanges.model_validate({"genders": ["male", "male"]})

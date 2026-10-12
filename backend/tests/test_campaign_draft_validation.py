import pytest

from app.campaigns.models import CampaignDraft
from app.campaigns.reference_repository import load_catalogue
from app.campaigns.validation import (
    CampaignDraftPolicyError,
    add_required_review_language,
    validate_campaign_draft_policy,
)


def valid_draft(**updates) -> CampaignDraft:
    values = {
        "name": "Retirement Income Readiness Review",
        "description": "Invite clients to review retirement income assumptions.",
        "clientMessage": (
            "This educational invitation is not financial advice. Any next step "
            "requires an individual suitability review with your adviser."
        ),
        "criteria": {
            "ageGroups": ["55to64"],
            "genders": [],
            "cashBands": ["50kTo250k", "250kTo1m"],
        },
        "targetDemographicSummary": (
            "Clients nearing retirement across all genders with available assets."
        ),
        "rationale": {
            "ageGroups": "The retirement transition supports this age group.",
            "genders": "The objective is not gender-specific.",
            "cashBands": "Available assets make these bands a review hypothesis.",
        },
        "assumptions": ["Retirement timing and available assets must be confirmed."],
        "disclaimer": (
            "Educational information only, not financial advice; suitability depends "
            "on individual circumstances and adviser review."
        ),
    }
    values.update(updates)
    return CampaignDraft.model_validate(values)


def test_valid_draft_returns_concrete_review_warnings():
    validation = validate_campaign_draft_policy(
        "Encourage clients nearing retirement to review income readiness",
        valid_draft(),
        [],
    )
    assert validation.schema_valid is True
    assert validation.policy_valid is True
    assert validation.warnings == [
        "The draft contains 1 assumption(s) requiring adviser review."
    ]
    assert "confidence" not in validation.model_dump()


@pytest.mark.parametrize(
    ("field", "unsafe_text", "expected_code"),
    [
        ("description", "This delivers guaranteed returns.", "unsupported_claim"),
        ("description", "The fund provides a 7% return.", "unsupported_claim"),
        ("description", "The premium starts from SGD 100.", "unsupported_claim"),
        ("description", "This is MAS-approved.", "unsupported_claim"),
        (
            "description",
            "Automatically send and activate the campaign.",
            "unsupported_claim",
        ),
        ("description", "Contact client@example.com today.", "invalid_draft"),
        ("description", "Use account number ABCDE12345.", "invalid_draft"),
    ],
)
def test_rejects_unsafe_claims_actions_and_personal_data(field, unsafe_text, expected_code):
    with pytest.raises(CampaignDraftPolicyError) as exc:
        validate_campaign_draft_policy(
            "Review retirement readiness",
            valid_draft(**{field: unsafe_text}),
            [],
        )
    assert exc.value.code == expected_code


def test_allows_clearly_negated_guarantee_and_risk_free_language():
    draft = valid_draft(
        clientMessage=(
            "This educational invitation is not financial advice. No outcome is "
            "guaranteed and it is not risk-free. Any next step requires an "
            "individual suitability review with your adviser."
        ),
        disclaimer=(
            "Educational information only and not financial advice. There are no "
            "guaranteed investment returns and no risk-free outcomes; suitability "
            "depends on individual circumstances and adviser review."
        ),
    )
    reference = next(
        entry for entry in load_catalogue().entries
        if entry.referenceId == "campaign-pattern-retirement-001"
    )

    result = validate_campaign_draft_policy(
        "Review retirement readiness", draft, [reference]
    )

    assert result.policy_valid is True


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "No doubt, guaranteed returns make this attractive.",
        "This is not only guaranteed but also risk-free.",
        "We do not promise a 7% return.",
    ],
)
def test_negation_cannot_hide_affirmative_or_invented_numeric_claims(unsafe_text):
    with pytest.raises(CampaignDraftPolicyError) as exc:
        validate_campaign_draft_policy(
            "Review retirement readiness",
            valid_draft(description=unsafe_text),
            [],
        )
    assert exc.value.code == "unsupported_claim"
    assert exc.value.field == "description"
    assert exc.value.rule in {"guarantee_claim", "percentage_claim"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("disclaimer", "Please speak to us for more information."),
        ("clientMessage", "Please contact us to discuss retirement."),
    ],
)
def test_requires_educational_and_individual_review_language(field, value):
    with pytest.raises(CampaignDraftPolicyError) as exc:
        validate_campaign_draft_policy(
            "Review retirement readiness", valid_draft(**{field: value}), []
        )
    assert exc.value.code == "missing_disclaimer"


def test_standard_review_language_is_added_only_to_incomplete_fields():
    draft = valid_draft(disclaimer="Please speak to your adviser before acting.")

    normalized, warnings = add_required_review_language(draft)

    assert normalized.clientMessage == draft.clientMessage
    assert normalized.disclaimer.startswith(draft.disclaimer)
    assert "educational" in normalized.disclaimer
    assert "does not constitute financial advice" in normalized.disclaimer
    assert "suitability assessment" in normalized.disclaimer
    assert warnings == [
        "Standard review language was added to disclaimer and requires adviser review."
    ]


def test_rejects_targeting_text_that_contradicts_structured_criteria():
    with pytest.raises(CampaignDraftPolicyError) as exc:
        validate_campaign_draft_policy(
            "Review retirement readiness",
            valid_draft(targetDemographicSummary="Women nearing retirement."),
            [],
        )
    assert exc.value.code == "inconsistent_targeting"


def test_rejects_composite_target_description_that_omits_a_structured_band():
    with pytest.raises(CampaignDraftPolicyError) as exc:
        validate_campaign_draft_policy(
            "Review retirement readiness",
            valid_draft(targetDemographicSummary="Clients aged 55 and above."),
            [],
        )
    assert exc.value.code == "inconsistent_targeting"


def test_applies_prohibited_claims_from_cited_catalogue_entries():
    healthcare_reference = next(
        entry for entry in load_catalogue().entries
        if entry.referenceId == "campaign-pattern-retirement-002"
    )
    with pytest.raises(CampaignDraftPolicyError) as exc:
        validate_campaign_draft_policy(
            "Review retirement healthcare readiness",
            valid_draft(description="Offer full medical coverage to every client."),
            [healthcare_reference],
        )
    assert exc.value.code == "unsupported_claim"


def test_warns_about_undefined_high_value_and_unsupported_restrictions():
    draft = valid_draft(
        criteria={
            "ageGroups": ["55to64"],
            "genders": ["female"],
            "cashBands": ["above1m"],
        },
        targetDemographicSummary="Women aged 55 to 64 with above SGD 1m cash.",
        rationale={
            "ageGroups": "Ages 55 to 64 are selected.",
            "genders": "Women are selected for this campaign.",
            "cashBands": "Above SGD 1m is selected as a hypothesis.",
        },
    )
    validation = validate_campaign_draft_policy(
        "Create a high-value client education campaign", draft, []
    )
    assert "The objective uses 'high-value' without defining a threshold." in validation.warnings
    assert "The objective does not explicitly support the gender restriction." in validation.warnings
    assert "The objective does not explicitly support the age restriction." in validation.warnings
    assert "The objective does not explicitly support the cash-band restriction." in validation.warnings

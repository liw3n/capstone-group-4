import pytest
from pydantic import ValidationError

from app.campaigns.criteria import criteria_from_storage, criteria_to_storage
from app.campaigns.models import CampaignCriteriaPayload, CampaignDraftCriteria


CANONICAL = {
    "ageGroups": ["under35", "35to44", "45to54", "55to64", "65plus"],
    "genders": ["male", "female"],
    "cashBands": ["under50k", "50kTo250k", "250kTo1m", "above1m"],
}

STORED = {
    "ageGroups": ["under35", "35-44", "45-54", "55-64", "65plus"],
    "genders": ["Male", "Female"],
    "cashBands": ["under50k", "50k-250k", "250k-1m", "above1m"],
}


def test_every_campaign_criteria_value_round_trips_through_storage():
    assert criteria_to_storage(CANONICAL) == STORED
    assert criteria_from_storage(STORED) == CANONICAL


def test_empty_unrestricted_dimensions_round_trip_without_inference():
    empty = {"ageGroups": [], "genders": [], "cashBands": []}
    assert criteria_from_storage(criteria_to_storage(empty)) == empty


@pytest.mark.parametrize(
    "criteria",
    [
        {**CANONICAL, "ageGroups": ["35-44"]},
        {**CANONICAL, "genders": ["Male"]},
        {**CANONICAL, "cashBands": ["250k-1m"]},
    ],
)
def test_generation_contract_rejects_storage_only_values(criteria):
    with pytest.raises(ValidationError):
        CampaignDraftCriteria.model_validate(criteria)
    with pytest.raises(ValidationError):
        CampaignCriteriaPayload.model_validate(criteria)


def test_model_facing_json_schema_contains_only_canonical_values():
    properties = CampaignDraftCriteria.model_json_schema()["properties"]
    assert properties["ageGroups"]["items"]["enum"] == CANONICAL["ageGroups"]
    assert properties["genders"]["items"]["enum"] == CANONICAL["genders"]
    assert properties["cashBands"]["items"]["enum"] == CANONICAL["cashBands"]


@pytest.mark.parametrize(
    "criteria",
    [
        {**STORED, "ageGroups": ["unknown"]},
        {**STORED, "genders": ["FEMALE"]},
        {**STORED, "cashBands": ["250kTo1m", "250k-1m"]},
        {**STORED, "ageGroups": "35-44"},
    ],
)
def test_storage_conversion_fails_closed_for_invalid_or_duplicate_values(criteria):
    with pytest.raises(ValueError):
        criteria_from_storage(criteria)

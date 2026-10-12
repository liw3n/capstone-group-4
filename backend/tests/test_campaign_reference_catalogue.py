import json

import pytest

from app.campaigns.reference_repository import CatalogueConfigurationError, load_catalogue


def test_checked_in_catalogue_is_versioned_approved_and_covers_all_categories():
    catalogue = load_catalogue()
    assert catalogue.catalogueVersion == 1
    assert 10 <= len(catalogue.entries) <= 20
    assert {entry.category for entry in catalogue.entries} == {
        "retirement", "protection", "education", "legacy", "property", "other"
    }
    assert all(entry.approvalStatus == "approved" for entry in catalogue.entries)
    assert all(entry.tenantIds == ["pulse-demo"] for entry in catalogue.entries)


@pytest.mark.parametrize("mutation", ["duplicate", "version", "date"])
def test_catalogue_loader_fails_fast_on_invalid_governance_data(tmp_path, mutation):
    raw = load_catalogue().model_dump(mode="json")
    if mutation == "duplicate":
        raw["entries"][1]["referenceId"] = raw["entries"][0]["referenceId"]
    elif mutation == "version":
        raw["entries"][0]["version"] = 0
    else:
        raw["entries"][0]["validUntil"] = "2025-12-31"
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogueConfigurationError):
        load_catalogue(path)

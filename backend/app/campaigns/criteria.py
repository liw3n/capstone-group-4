"""Campaign targeting criteria vocabularies and storage-boundary conversion.

The application, HTTP API, frontend and campaign-generation tools use the
canonical values below.  The current prototype ``campaign.audience_criteria``
JSON uses a separate display-oriented storage vocabulary.  Keep translation at
the repository boundary so storage changes cannot alter model-facing schemas.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypeVar, cast

AgeGroup = Literal["under35", "35to44", "45to54", "55to64", "65plus"]
Gender = Literal["male", "female"]
CashBand = Literal["under50k", "50kTo250k", "250kTo1m", "above1m"]

StorageAgeGroup = Literal["under35", "35-44", "45-54", "55-64", "65plus"]
StorageGender = Literal["Male", "Female"]
StorageCashBand = Literal["under50k", "50k-250k", "250k-1m", "above1m"]

_AGE_FROM_STORAGE: dict[str, AgeGroup] = {
    "under35": "under35",
    "35-44": "35to44",
    "35to44": "35to44",
    "45-54": "45to54",
    "45to54": "45to54",
    "55-64": "55to64",
    "55to64": "55to64",
    "65plus": "65plus",
}
_GENDER_FROM_STORAGE: dict[str, Gender] = {
    "Male": "male",
    "Female": "female",
    "male": "male",
    "female": "female",
}
_CASH_FROM_STORAGE: dict[str, CashBand] = {
    "under50k": "under50k",
    "50k-250k": "50kTo250k",
    "50kTo250k": "50kTo250k",
    "250k-1m": "250kTo1m",
    "250kTo1m": "250kTo1m",
    "above1m": "above1m",
}

_AGE_TO_STORAGE: dict[AgeGroup, StorageAgeGroup] = {
    "under35": "under35",
    "35to44": "35-44",
    "45to54": "45-54",
    "55to64": "55-64",
    "65plus": "65plus",
}
_GENDER_TO_STORAGE: dict[Gender, StorageGender] = {
    "male": "Male",
    "female": "Female",
}
_CASH_TO_STORAGE: dict[CashBand, StorageCashBand] = {
    "under50k": "under50k",
    "50kTo250k": "50k-250k",
    "250kTo1m": "250k-1m",
    "above1m": "above1m",
}

CanonicalValue = TypeVar("CanonicalValue", AgeGroup, Gender, CashBand)
StorageValue = TypeVar("StorageValue", StorageAgeGroup, StorageGender, StorageCashBand)


def _convert_values(
    values: Any,
    mapping: Mapping[str, CanonicalValue],
    field_name: str,
) -> list[CanonicalValue]:
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    converted: list[CanonicalValue] = []
    for value in values:
        if not isinstance(value, str) or value not in mapping:
            raise ValueError(f"{field_name} contains an unsupported value")
        converted.append(mapping[value])
    if len(converted) != len(set(converted)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return converted


def _storage_values(
    values: Any,
    mapping: Mapping[CanonicalValue, StorageValue],
    field_name: str,
) -> list[StorageValue]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a list")
    converted: list[StorageValue] = []
    for value in values:
        if not isinstance(value, str) or value not in mapping:
            raise ValueError(f"{field_name} contains an unsupported value")
        converted.append(mapping[cast(CanonicalValue, value)])
    if len(converted) != len(set(converted)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return converted


def criteria_from_storage(raw: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return canonical criteria from current or legacy stored JSON values."""
    return {
        "ageGroups": list(
            _convert_values(raw.get("ageGroups", []), _AGE_FROM_STORAGE, "ageGroups")
        ),
        "genders": list(
            _convert_values(raw.get("genders", []), _GENDER_FROM_STORAGE, "genders")
        ),
        "cashBands": list(
            _convert_values(raw.get("cashBands", []), _CASH_FROM_STORAGE, "cashBands")
        ),
    }


def criteria_to_storage(raw: Mapping[str, Any]) -> dict[str, list[str]]:
    """Translate strict canonical criteria to the current campaign-table JSON."""
    return {
        "ageGroups": list(
            _storage_values(raw.get("ageGroups", []), _AGE_TO_STORAGE, "ageGroups")
        ),
        "genders": list(
            _storage_values(raw.get("genders", []), _GENDER_TO_STORAGE, "genders")
        ),
        "cashBands": list(
            _storage_values(raw.get("cashBands", []), _CASH_TO_STORAGE, "cashBands")
        ),
    }

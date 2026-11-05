"""Validated overlap filters over campaign definitions, without reading clients."""
from datetime import date
from math import inf
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.campaigns.repository import Campaign


AGE_INTERVALS = {
    "under35": (0, 34), "35to44": (35, 44), "45to54": (45, 54),
    "55to64": (55, 64), "65plus": (65, inf),
}
CASH_INTERVALS = {
    "under50k": (0, 50_000), "50kTo250k": (50_000, 250_000),
    "250kTo1m": (250_000, 1_000_000), "above1m": (1_000_000, inf),
}


class CampaignFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_min: int | None = Field(default=None, ge=0, le=130, strict=True)
    age_max: int | None = Field(default=None, ge=0, le=130, strict=True)
    genders: list[Literal["Male", "Female"]] | None = Field(default=None, max_length=2)
    cash_min: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)
    cash_max: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)
    cash_min_exclusive: bool = Field(default=False, strict=True)
    cash_max_exclusive: bool = Field(default=False, strict=True)
    campaign_codes: list[str] | None = Field(default=None, max_length=100)
    name_contains: str | None = Field(default=None, min_length=1, max_length=200)
    description_contains: str | None = Field(default=None, min_length=1, max_length=500)
    start_date_from: date | None = None
    start_date_to: date | None = None
    end_date_from: date | None = None
    end_date_to: date | None = None

    @model_validator(mode="after")
    def ordered_ranges(self):
        for minimum, maximum in (
            (self.age_min, self.age_max), (self.cash_min, self.cash_max),
            (self.start_date_from, self.start_date_to), (self.end_date_from, self.end_date_to),
        ):
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("Filter minimum must not exceed maximum")
        if self.cash_min_exclusive and self.cash_min is None:
            raise ValueError("Exclusive cash minimum requires a bound")
        if self.cash_max_exclusive and self.cash_max is None:
            raise ValueError("Exclusive cash maximum requires a bound")
        if (self.cash_min is not None and self.cash_min == self.cash_max
                and (self.cash_min_exclusive or self.cash_max_exclusive)):
            raise ValueError("Cash filter range is empty")
        if self.campaign_codes is not None and any(
            not code.strip() or len(code) > 50 for code in self.campaign_codes
        ):
            raise ValueError("Invalid campaign code")
        return self


def _overlap(lower, upper, minimum, maximum, *, upper_open=False,
             minimum_open=False, maximum_open=False) -> bool:
    minimum = 0 if minimum is None else minimum
    maximum = inf if maximum is None else maximum
    if upper < minimum or maximum < lower:
        return False
    if upper == minimum and (upper_open or minimum_open):
        return False
    if maximum == lower and maximum_open:
        return False
    return True


def matches_filters(campaign: Campaign, filters: CampaignFilters) -> bool:
    """AND requested dimensions; OR stored bands/custom ranges within each.

    A campaign without restrictions in a dimension accepts every requested value.
    """
    criteria = campaign.criteria
    if filters.age_min is not None or filters.age_max is not None:
        intervals = [AGE_INTERVALS[group] for group in criteria.age_groups]
        if criteria.age_min is not None or criteria.age_max is not None:
            intervals.append((criteria.age_min or 0,
                              inf if criteria.age_max is None else criteria.age_max))
        if intervals and not any(_overlap(lo, hi, filters.age_min, filters.age_max)
                                 for lo, hi in intervals):
            return False
    if filters.genders and criteria.genders and not (
        {gender.lower() for gender in criteria.genders}
        & {gender.lower() for gender in filters.genders}
    ):
        return False
    if filters.cash_min is not None or filters.cash_max is not None:
        intervals = [(lo, hi, True) for band in criteria.cash_bands
                     for lo, hi in [CASH_INTERVALS[band]]]
        if criteria.cash_min is not None or criteria.cash_max is not None:
            intervals.append((criteria.cash_min or 0,
                              inf if criteria.cash_max is None else criteria.cash_max, False))
        if intervals and not any(_overlap(
            lo, hi, filters.cash_min, filters.cash_max, upper_open=upper_open,
            minimum_open=filters.cash_min_exclusive, maximum_open=filters.cash_max_exclusive,
        ) for lo, hi, upper_open in intervals):
            return False
    if filters.campaign_codes is not None and campaign.campaign_code.casefold() not in {
        code.casefold() for code in filters.campaign_codes
    }:
        return False
    for field in ("name", "description"):
        term = getattr(filters, field + "_contains")
        if term is not None and term.casefold() not in (getattr(campaign, field) or "").casefold():
            return False
    for field in ("start_date", "end_date"):
        value = getattr(campaign, field)
        lower, upper = getattr(filters, field + "_from"), getattr(filters, field + "_to")
        if lower is not None and (value is None or value < lower):
            return False
        if upper is not None and (value is None or value > upper):
            return False
    return True

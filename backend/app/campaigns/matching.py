"""Read-only, deterministic campaign eligibility. No ranking or financial advice."""
from datetime import date
from math import isfinite

from app.campaigns.repository import (
    Client, Criteria, DEMO_DATE, RequestScope, get_campaign, list_clients_for_fa,
    require_active,
)

MAX_RESULTS = 100
AGE_LABELS = {
    "under35": "under 35", "35to44": "35 - 44", "45to54": "45 - 54",
    "55to64": "55 - 64", "65plus": "65 and above",
}
CASH_LABELS = {
    "under50k": "below S$50,000", "50kTo250k": "S$50,000 to below S$250,000",
    "250kTo1m": "S$250,000 to below S$1,000,000", "above1m": "S$1,000,000 and above",
}


def age_from_dob(dob: str | None, as_of: date = DEMO_DATE) -> int | None:
    try:
        born = date.fromisoformat(dob or "")
        if born.isoformat() != dob:
            return None
    except (ValueError, TypeError):
        return None
    age = as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))
    return age if 0 <= age < 130 else None


def age_group(age: int) -> str:
    for ceiling, group in ((35, "under35"), (45, "35to44"), (55, "45to54"), (65, "55to64")):
        if age < ceiling:
            return group
    return "65plus"


def valid_cash(cash: float | None) -> bool:
    return isinstance(cash, (int, float)) and not isinstance(cash, bool) and isfinite(cash) and cash >= 0


def cash_band(cash: float) -> str:
    for floor, band in ((1_000_000, "above1m"), (250_000, "250kTo1m"), (50_000, "50kTo250k")):
        if cash >= floor:
            return band
    return "under50k"


def range_active(minimum, maximum) -> bool:
    return minimum is not None or maximum is not None


def in_range(value, minimum, maximum) -> bool:
    return (range_active(minimum, maximum)
            and (minimum is None or value >= minimum)
            and (maximum is None or value <= maximum))


def explain_match(client: Client, criteria: Criteria, as_of: date = DEMO_DATE) -> dict:
    age_filter = bool(criteria.age_groups) or range_active(criteria.age_min, criteria.age_max)
    cash_filter = bool(criteria.cash_bands) or range_active(criteria.cash_min, criteria.cash_max)
    age = age_from_dob(client.dob, as_of)
    gaps = []
    if age_filter and age is None:
        gaps.append("date_of_birth")
    if criteria.genders and client.gender not in ("male", "female"):
        gaps.append("gender")
    if cash_filter and not valid_cash(client.available_cash):
        gaps.append("available_cash")
    # Missing-first semantics match targeting.ts: selected missing fields remain
    # visible even if another known field fails.
    if gaps:
        return {"status": "incomplete", "missing_fields": gaps}

    reasons = []
    if age_filter:
        group = age_group(age)
        if group in criteria.age_groups:
            reasons.append(f"Age {age} matches the campaign age group ({AGE_LABELS[group]})")
        elif in_range(age, criteria.age_min, criteria.age_max):
            reasons.append(f"Age {age} matches the campaign's inclusive custom age range")
        else:
            return {"status": "excluded"}
    if criteria.genders:
        if client.gender not in criteria.genders:
            return {"status": "excluded"}
        reasons.append(f"Gender {client.gender} matches the campaign criterion")
    if cash_filter:
        cash = client.available_cash
        amount = "S$" + f"{cash:,.0f}"
        band = cash_band(cash)
        if band in criteria.cash_bands:
            reasons.append(f"Available cash of {amount} matches the cash criterion ({CASH_LABELS[band]})")
        elif in_range(cash, criteria.cash_min, criteria.cash_max):
            reasons.append(f"Available cash of {amount} matches the campaign's inclusive custom cash range")
        else:
            return {"status": "excluded"}
    if not reasons:
        reasons.append("Campaign has no age, gender or cash filters; client belongs to this adviser's demo book")
    return {"status": "matched", "reasons": reasons}


def recommend_clients_for_campaign(campaign_id: str, scope: RequestScope, limit: int = MAX_RESULTS) -> dict:
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be an integer from 1 to {MAX_RESULTS}")
    campaign = get_campaign(campaign_id, scope)
    require_active(campaign)
    clients = list_clients_for_fa(scope)
    matched, incomplete = [], []
    excluded_count = 0
    for client in clients:
        result = explain_match(client, campaign.criteria)
        entry = {"contact_id": client.contact_id, "name": client.name}
        if result["status"] == "matched":
            matched.append({**entry, "reasons": result["reasons"]})
        elif result["status"] == "incomplete":
            incomplete.append({**entry, "missing_fields": result["missing_fields"]})
        else:
            excluded_count += 1
    # Stable ID order is presentation order, not a recommendation ranking.
    matched.sort(key=lambda item: item["contact_id"])
    incomplete.sort(key=lambda item: item["contact_id"])
    return {
        "data_source": "synthetic",
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.name,
        "as_of_date": DEMO_DATE.isoformat(),
        "evaluated_count": len(clients),
        "matched_count": len(matched),
        "clients": matched[:limit],
        "returned_count": min(len(matched), limit),
        "truncated": len(matched) > limit,
        "incomplete_count": len(incomplete),
        "incomplete_clients": incomplete[:limit],
        "incomplete_truncated": len(incomplete) > limit,
        "excluded_count": excluded_count,
        "disclaimer": "Synthetic campaign criteria matches for adviser review, not a product suitability assessment or financial advice. Outreach requires separate consent checks and confirmation.",
    }

"""Shared handler for read-only, request-scoped campaign discovery."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.campaigns import clock
from app.tools.campaign_catalogue_api import fetch_campaigns
from app.campaigns.discovery_filters import CampaignFilters, matches_filters
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN,
    CampaignStorageUnavailable,
    RequestScope,
)

CampaignField = Literal[
    "campaign_id", "name", "description", "start_date", "end_date", "age_groups", "genders",
    "cash_bands", "age_min", "age_max", "cash_min", "cash_max", "status",
]
CampaignId = Annotated[str, Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)]
CampaignName = Annotated[str, Field(min_length=1, max_length=255)]
DEFAULT_FIELDS = [
    "name", "description", "start_date", "end_date", "age_groups", "genders", "cash_bands",
]
FIELD_LABELS = {"name": "Campaign Name", "age_groups": "Age Group"}
AGE_LABELS = {
    "under35": "Under 35", "35to44": "35–44", "45to54": "45–54",
    "55to64": "55–64", "65plus": "65 and above",
}
CASH_LABELS = {
    "under50k": "Below S$50,000", "50kTo250k": "S$50,000 to below S$250,000",
    "250kTo1m": "S$250,000 to below S$1,000,000", "above1m": "S$1,000,000 and above",
}
DISCLAIMER = (
    "Campaign information for adviser review, not a product suitability "
    "assessment or financial advice. Outreach requires separate consent checks and confirmation."
)


class ActiveCampaignArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_ids: list[CampaignId] | None = Field(default=None, max_length=100)
    campaign_names: list[CampaignName] | None = Field(default=None, max_length=100)
    limit: int = Field(default=1000, ge=1, le=1000, strict=True)
    fields: list[CampaignField] | None = Field(default=None, min_length=1, max_length=13)
    filters: CampaignFilters | None = None


def current_date() -> date:
    return clock.current_date()


def _markdown_text(value: object) -> str:
    text = str(value)
    for character in ("\\", "`", "*", "_", "[", "]"):
        text = text.replace(character, "\\" + character)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("|", "&#124;").replace("\r", " ").replace("\n", " "))


def markdown_table(columns: list[str], rows: list[dict]) -> str:
    def cell(value: object) -> str:
        if value is None:
            return "Unknown"
        if isinstance(value, (tuple, list)):
            value = ", ".join(map(str, value)) or "Any"
        return _markdown_text(value)

    headers = [
        FIELD_LABELS.get(column, " ".join(
            "ID" if word == "id" else word.title() for word in column.split("_")
        ))
        for column in columns
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(cell(row[column]) for column in columns) + " |"
        for row in rows
    )
    return "\n".join(lines)


def _error(code: str, message: str) -> dict:
    return {"data_source": "synthetic", "error_code": code, "error": message}


def _audience_label(bands, labels, minimum, maximum, *, cash=False) -> str:
    parts = [labels[band] for band in bands]

    def number(value):
        return f"S${value:,}".removesuffix(".0") if cash else str(value)

    if minimum is not None and maximum is not None:
        parts.append(f"{number(minimum)}–{number(maximum)}")
    elif minimum is not None:
        parts.append(f"{number(minimum)} and above")
    elif maximum is not None:
        parts.append(f"Up to {number(maximum)}")
    return " or ".join(parts) or "Any"


def _filter_summary(filters: dict) -> str:
    parts = []
    if filters.get("age_min") is not None or filters.get("age_max") is not None:
        parts.append("Age: " + _audience_label([], {}, filters.get("age_min"), filters.get("age_max")))
    if filters.get("genders"):
        parts.append("Gender: " + ", ".join(filters["genders"]))
    cash = []
    for bound, inclusive, exclusive in (("min", "at least", "above"), ("max", "at most", "below")):
        value = filters.get("cash_" + bound)
        if value is not None:
            comparison = exclusive if filters.get(f"cash_{bound}_exclusive") else inclusive
            cash.append(f"{comparison} S${value:,}".removesuffix(".0"))
    if cash:
        parts.append("Cash: " + " and ".join(cash))
    for field in ("name", "description"):
        if field + "_contains" in filters:
            parts.append(f"{field.title()} contains: {filters[field + '_contains']}")
    for field in ("start_date", "end_date"):
        bounds = [f"{side} {filters[field + '_' + side]}" for side in ("from", "to")
                  if field + "_" + side in filters]
        if bounds:
            parts.append(field.replace("_", " ").title() + ": " + " ".join(bounds))
    return _markdown_text("; ".join(parts))


def render_active_campaigns(payload: dict) -> str:
    """Render the retrieved snapshot directly, including a browser Excel action."""
    if "error" in payload:
        return "Unable to retrieve active campaigns: " + str(payload["error"])
    as_of = date.fromisoformat(payload["as_of_date"])
    sections = [f"**Current date: {as_of.day} {as_of:%B %Y} (Singapore)**"]
    if payload.get("filters"):
        sections.append("Filters: " + _filter_summary(payload["filters"])
            + ". Audience filters match overlapping eligibility ranges; full campaign criteria are shown.")
    if not payload["rows"]:
        sections.append("No active campaigns match your filters.")
    sections.append(payload["table"])
    sections.append("[Download Excel (.xlsx)](#active-campaigns-excel)")
    if payload["truncated"]:
        sections.append(f"Showing {payload['returned_count']} of {payload['total_count']} matching active campaigns. "
                        "The Excel download contains the displayed rows.")
    return "\n\n".join(sections)


def execute_get_active_campaigns(arguments: dict, metadata: dict | None) -> dict:
    """Validate adviser context and filters, then return active campaigns as a table."""
    context = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    if not isinstance(context, dict):
        return _error("missing_context", "Adviser request context is required")
    try:
        scope = RequestScope(fa_id=context.get("fa_id"), tenant_id=context.get("tenant_id"))
    except ValueError:
        return _error("missing_context", "Adviser request context is required")
    try:
        query = ActiveCampaignArguments.model_validate(arguments)
    except ValidationError:
        return _error("invalid_arguments", "Invalid tool arguments")

    as_of = current_date()
    try:
        campaigns = fetch_campaigns(scope)
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    fields = query.fields or DEFAULT_FIELDS
    # Preserve field order and always identify a campaign by its name.
    columns = list(dict.fromkeys(fields if "name" in fields else ["name", *fields]))
    rows = []
    names = {name.casefold() for name in query.campaign_names} if query.campaign_names is not None else None
    for campaign in campaigns:
        if campaign.status != "active":
            continue
        if query.campaign_ids is not None and campaign.campaign_id not in query.campaign_ids:
            continue
        if names is not None and campaign.name.casefold() not in names:
            continue
        if query.filters is not None and not matches_filters(campaign, query.filters):
            continue
        criteria = campaign.criteria
        values = {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "description": campaign.description,
            "status": campaign.status,
            "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
            "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
            **vars(campaign.criteria),
            "age_groups": _audience_label(criteria.age_groups, AGE_LABELS, criteria.age_min, criteria.age_max),
            "genders": ", ".join(gender.title() for gender in criteria.genders) or "Any",
            "cash_bands": _audience_label(criteria.cash_bands, CASH_LABELS, criteria.cash_min, criteria.cash_max, cash=True),
        }
        rows.append({
            column: list(values[column]) if isinstance(values[column], tuple) else values[column]
            for column in columns
        })

    returned = rows[:query.limit]
    return {
        "data_source": "synthetic",
        "as_of_date": as_of.isoformat(),
        "filters": query.filters.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        if query.filters is not None else {},
        "columns": columns,
        "rows": returned,
        "table": markdown_table(columns, returned),
        "total_count": len(rows),
        "returned_count": len(returned),
        "truncated": len(rows) > query.limit,
        "disclaimer": DISCLAIMER,
    }

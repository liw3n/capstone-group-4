"""Read-only synthetic campaign contact performance for one adviser."""
from datetime import date, datetime, time, timedelta
import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.campaigns import repository
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN, Campaign, CampaignAmbiguous, CampaignStorageUnavailable,
    CampaignUnavailable, RequestScope,
)

SINGAPORE = ZoneInfo("Asia/Singapore")


class ContactPerformanceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign: str | None = Field(default=None, min_length=1, max_length=255)
    period: Literal["this_week", "last_week"] = "this_week"


def current_time() -> datetime:
    return datetime.now(SINGAPORE)


def _error(code: str, message: str) -> dict:
    return {"data_source": "synthetic", "error_code": code, "error": message}


def _resolve_campaign(campaign_query: str, selected_id: str | None,
                      scope: RequestScope) -> Campaign:
    if selected_id is not None:
        return repository.get_campaign(selected_id, scope)
    if campaign_query and len(campaign_query) <= 69:
        try:
            return repository.get_campaign(campaign_query, scope)
        except CampaignUnavailable:
            pass
    return repository.get_campaign_by_name(campaign_query, scope)


def _state(campaign: Campaign, as_of_date: date) -> tuple[str, str]:
    if campaign.status == "draft":
        return "draft", "is in draft"
    if as_of_date < campaign.start_date:
        return "upcoming", "has not started"
    if campaign.status == "completed" or as_of_date > campaign.end_date:
        return "completed", "has ended"
    if campaign.status == "paused":
        return "paused", "is paused"
    return "ongoing", "is ongoing"


def execute_contact_performance(arguments: dict, metadata: dict | None) -> dict:
    context = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    if not isinstance(context, dict):
        return _error("missing_context", "Adviser request context is required")
    try:
        scope = RequestScope(fa_id=context.get("fa_id"), tenant_id=context.get("tenant_id"))
    except ValueError:
        return _error("missing_context", "Adviser request context is required")
    try:
        query = ContactPerformanceArguments.model_validate(arguments)
    except ValidationError:
        return _error("invalid_arguments", "Invalid tool arguments")

    selected_id = metadata.get("campaign_id")
    if selected_id is not None and (
        not isinstance(selected_id, str)
        or re.fullmatch(CAMPAIGN_ID_PATTERN, selected_id) is None
    ):
        return _error("invalid_campaign_context", "Selected campaign context is invalid")
    campaign_query = query.campaign.strip() if query.campaign is not None else ""
    if selected_id is None and not campaign_query:
        return _error("missing_campaign", "Select a campaign or name one in the current message")

    try:
        campaign = _resolve_campaign(campaign_query, selected_id, scope)
        now = current_time().astimezone(SINGAPORE)
        today = now.date()
        period_start = datetime.combine(campaign.start_date, time.min, SINGAPORE)
        campaign_end = datetime.combine(campaign.end_date + timedelta(days=1), time.min,
                                        SINGAPORE)
        period_end = min(now, campaign_end)
        week_start_date = today - timedelta(days=today.weekday())
        week_start = datetime.combine(week_start_date, time.min, SINGAPORE)
        last_week_start_date = week_start_date - timedelta(days=7)
        last_week_start = datetime.combine(last_week_start_date, time.min, SINGAPORE)
        last_week_end_date = week_start_date - timedelta(days=1)
        counts = ((0, 0, 0, 0, 0) if period_end <= period_start else
                  repository.count_campaign_contacts(scope, campaign.campaign_id,
                                                     period_start, period_end, week_start,
                                                     last_week_start))
    except CampaignUnavailable as exc:
        return _error("campaign_unavailable", str(exc))
    except CampaignAmbiguous as exc:
        return _error("campaign_ambiguous", str(exc))
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    total, this_week, first_this_week, last_week, first_last_week = counts
    state, state_words = _state(campaign, today)
    date_words = f"{today.day} {today:%B %Y}"
    if query.period == "last_week":
        start_words = f"{last_week_start_date.day} {last_week_start_date:%B %Y}"
        end_words = f"{last_week_end_date.day} {last_week_end_date:%B %Y}"
        summary = (f"{campaign.name} {state_words}. {last_week} "
                   f"{'client was' if last_week == 1 else 'clients were'} contacted "
                   f"last week ({start_words} to {end_words}).")
    else:
        summary = (f"{campaign.name} {state_words}. As of {date_words}, "
                   f"{total} {'client has' if total == 1 else 'clients have'} been contacted. "
                   f"{this_week} {'was' if this_week == 1 else 'were'} contacted this week.")
    return {
        "data_source": "synthetic",
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.name,
        "campaign_status": campaign.status,
        "reporting_state": state,
        "campaign_start_date": campaign.start_date.isoformat(),
        "campaign_end_date": campaign.end_date.isoformat(),
        "reporting_period_start": campaign.start_date.isoformat(),
        "reporting_period_end": (min(today, campaign.end_date).isoformat()
                                 if today >= campaign.start_date else None),
        "as_of_date": today.isoformat(),
        "as_of_time": now.isoformat(),
        "requested_period": query.period,
        "week_start_date": week_start_date.isoformat(),
        "last_week_start_date": last_week_start_date.isoformat(),
        "last_week_end_date": last_week_end_date.isoformat(),
        "contacted_clients_total": total,
        "contacted_clients_this_week": this_week,
        "first_contacted_clients_this_week": first_this_week,
        "contacted_clients_last_week": last_week,
        "first_contacted_clients_last_week": first_last_week,
        "summary": summary,
        "metric_definition": (
            "Each count is distinct clients for this adviser and campaign. "
            "Weekly contacts include repeat contacts within that week; first-contacted "
            "counts clients whose earliest campaign contact is in that week. "
            "Last week is the previous Monday through Sunday in Singapore time. "
            "Only recorded synthetic contact events are included."
        ),
    }

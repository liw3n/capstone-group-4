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
    period: Literal["this_week", "last_week", "specific_week"] = "this_week"
    week_of: str | None = Field(default=None, min_length=10, max_length=10,
                                pattern=r"^\d{4}-\d{2}-\d{2}$")


class ContactRankingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: Literal["campaign_to_date", "this_week", "last_week"] = "campaign_to_date"


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
    requested_week_date = None
    if query.period == "specific_week":
        if query.week_of is None:
            return _error("invalid_arguments", "week_of is required for a specific week")
        try:
            requested_week_date = date.fromisoformat(query.week_of)
        except ValueError:
            return _error("invalid_arguments", "week_of must be a valid YYYY-MM-DD date")
    elif query.week_of is not None:
        return _error("invalid_arguments", "week_of is only used for a specific week")
    requested_week_start_date = (requested_week_date -
                                 timedelta(days=requested_week_date.weekday())
                                 if requested_week_date is not None else None)
    requested_week_end_date = (requested_week_start_date + timedelta(days=6)
                               if requested_week_start_date is not None else None)

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
        if requested_week_start_date is not None and requested_week_start_date > today:
            return _error("future_period", "The requested week has not started")
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
        requested_week_count = None
        if requested_week_start_date is not None:
            requested_start = max(
                period_start, datetime.combine(requested_week_start_date, time.min, SINGAPORE)
            )
            requested_end = min(
                period_end,
                datetime.combine(requested_week_end_date + timedelta(days=1),
                                 time.min, SINGAPORE),
            )
            requested_week_count = (
                0 if requested_end <= requested_start else
                repository.count_campaign_contacts_in_period(
                    scope, campaign.campaign_id, requested_start, requested_end
                )
            )
    except CampaignUnavailable as exc:
        return _error("campaign_unavailable", str(exc))
    except CampaignAmbiguous as exc:
        return _error("campaign_ambiguous", str(exc))
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    total, this_week, first_this_week, last_week, first_last_week = counts
    state, state_words = _state(campaign, today)
    date_words = f"{today.day} {today:%B %Y}"
    if query.period == "specific_week":
        start_words = (f"{requested_week_start_date.day} "
                       f"{requested_week_start_date:%B %Y}")
        end_words = (f"{requested_week_end_date.day} "
                     f"{requested_week_end_date:%B %Y}")
        summary = (f"{campaign.name} {state_words}. {requested_week_count} "
                   f"{'client was' if requested_week_count == 1 else 'clients were'} "
                   f"contacted during the week of {start_words} to {end_words}.")
    elif query.period == "last_week":
        start_words = f"{last_week_start_date.day} {last_week_start_date:%B %Y}"
        end_words = f"{last_week_end_date.day} {last_week_end_date:%B %Y}"
        summary = (f"{campaign.name} {state_words}. {last_week} "
                   f"{'client was' if last_week == 1 else 'clients were'} contacted "
                   f"last week ({start_words} to {end_words}).")
    else:
        summary = (f"{campaign.name} {state_words}. As of {date_words}, "
                   f"{total} {'client has' if total == 1 else 'clients have'} been contacted. "
                   f"{this_week} {'was' if this_week == 1 else 'were'} contacted this week.")
    result = {
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
            "A specific week is the Monday through Sunday containing week_of. "
            "Only recorded synthetic contact events are included."
        ),
    }
    if requested_week_date is not None:
        result.update({
            "week_of": requested_week_date.isoformat(),
            "requested_week_start_date": requested_week_start_date.isoformat(),
            "requested_week_end_date": requested_week_end_date.isoformat(),
            "contacted_clients_requested_week": requested_week_count,
        })
    return result


def execute_contact_ranking(arguments: dict, metadata: dict | None) -> dict:
    context = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    if not isinstance(context, dict):
        return _error("missing_context", "Adviser request context is required")
    try:
        scope = RequestScope(fa_id=context.get("fa_id"), tenant_id=context.get("tenant_id"))
    except ValueError:
        return _error("missing_context", "Adviser request context is required")
    try:
        query = ContactRankingArguments.model_validate(arguments)
    except ValidationError:
        return _error("invalid_arguments", "Invalid tool arguments")

    now = current_time().astimezone(SINGAPORE)
    today = now.date()
    week_start_date = today - timedelta(days=today.weekday())
    week_start = datetime.combine(week_start_date, time.min, SINGAPORE)
    if query.period == "last_week":
        period_start = week_start - timedelta(days=7)
        period_end = week_start
        period_end_date = week_start_date - timedelta(days=1)
        period_words = (f"last week ({period_start.day} {period_start:%B %Y} to "
                        f"{period_end_date.day} {period_end_date:%B %Y})")
    elif query.period == "this_week":
        period_start = week_start
        period_end = now
        period_end_date = today
        period_words = "this week"
    else:
        period_start = None
        period_end = now
        period_end_date = today
        period_words = f"as of {today.day} {today:%B %Y}"

    try:
        rows = repository.rank_campaigns_by_contacts(scope, period_start, period_end)
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    campaign_count = rows[0]["campaign_count"] if rows else 0
    visible = rows[:20]
    ranking = [{"campaign_id": row["campaign_id"], "campaign_name": row["name"],
                "campaign_status": row["status"],
                "contacted_clients": row["contacted_clients"]} for row in visible]
    highest = ranking[0]["contacted_clients"] if ranking else 0
    leaders = [row for row in ranking if row["contacted_clients"] == highest]
    leaders_truncated = bool(rows and rows[0]["tie_count"] > len(leaders))
    if not ranking:
        summary = "No campaigns are available to this adviser."
    elif highest == 0:
        summary = f"No recorded clients were contacted for any available campaign {period_words}."
    elif leaders_truncated:
        summary = (f"At least {len(leaders)} campaigns tie for the highest recorded "
                   f"contact count {period_words}: {highest} distinct clients each. "
                   "The full tie does not fit in this tool result.")
    elif len(leaders) == 1:
        summary = (f"{leaders[0]['campaign_name']} has the highest recorded contact count "
                   f"{period_words}: {highest} distinct clients.")
    else:
        names = ", ".join(row["campaign_name"] for row in leaders)
        summary = (f"{names} are tied for the highest recorded contact count "
                   f"{period_words}: {highest} distinct clients each.")
    return {
        "data_source": "synthetic",
        "metric": "distinct_clients_contacted",
        "requested_period": query.period,
        "period_start_date": period_start.date().isoformat() if period_start else None,
        "period_end_date": period_end_date.isoformat(),
        "as_of_time": now.isoformat(),
        "campaign_count": campaign_count,
        "ranking_truncated": campaign_count > len(ranking),
        "leaders_truncated": leaders_truncated,
        "ranked_campaigns": ranking,
        "leaders": leaders,
        "highest_contacted_clients": highest,
        "summary": summary,
        "metric_definition": (
            "Each campaign count is distinct clients with a recorded synthetic contact "
            "during the requested period and that campaign's own dates. Repeated contacts "
            "with one client count once per campaign. Campaigns without contacts count as zero. "
            "Only campaigns accessible to this adviser and tenant are compared."
        ),
    }

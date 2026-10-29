"""Read-only synthetic campaign membership and recorded email performance."""
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
    """The MCP tool name is retained for compatibility with existing chat clients."""

    model_config = ConfigDict(extra="forbid")
    campaign: str | None = Field(default=None, min_length=1, max_length=255)
    period: Literal["this_week", "last_week", "specific_week"] = "this_week"
    week_of: str | None = Field(default=None, min_length=10, max_length=10,
                                pattern=r"^\d{4}-\d{2}-\d{2}$")


class ContactRankingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: Literal["campaign_to_date", "this_week", "last_week"] = "campaign_to_date"
    metric: Literal["clients_emailed", "members_added"] = "clients_emailed"


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
    if campaign.start_date is not None and as_of_date < campaign.start_date:
        return "upcoming", "has not started"
    if campaign.status == "completed" or (
        campaign.end_date is not None and as_of_date > campaign.end_date
    ):
        return "completed", "has ended"
    if campaign.status == "paused":
        return "paused", "is paused"
    return "ongoing", "is ongoing"


def execute_contact_performance(arguments: dict, metadata: dict | None) -> dict:
    """Report member additions and cumulative email fields, never weekly contacts."""
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

    selected_id = metadata.get("campaign_id")
    if selected_id is not None and (
        not isinstance(selected_id, str)
        or re.fullmatch(CAMPAIGN_ID_PATTERN, selected_id) is None
    ):
        return _error("invalid_campaign_context", "Selected campaign context is invalid")
    campaign_query = query.campaign.strip() if query.campaign is not None else ""
    if selected_id is None and not campaign_query:
        return _error("missing_campaign", "Select a campaign or name one in the current message")

    now = current_time().astimezone(SINGAPORE)
    today = now.date()
    week_start_date = today - timedelta(days=today.weekday())
    week_start = datetime.combine(week_start_date, time.min, SINGAPORE)
    last_week_start_date = week_start_date - timedelta(days=7)
    last_week_start = datetime.combine(last_week_start_date, time.min, SINGAPORE)
    last_week_end_date = week_start_date - timedelta(days=1)
    requested_week_start_date = (
        requested_week_date - timedelta(days=requested_week_date.weekday())
        if requested_week_date is not None else None
    )
    requested_week_end_date = (
        requested_week_start_date + timedelta(days=6)
        if requested_week_start_date is not None else None
    )
    if requested_week_start_date is not None and requested_week_start_date > today:
        return _error("future_period", "The requested week has not started")
    requested_start = (
        datetime.combine(requested_week_start_date, time.min, SINGAPORE)
        if requested_week_start_date is not None else None
    )
    requested_end = (
        min(now, datetime.combine(requested_week_end_date + timedelta(days=1),
                                  time.min, SINGAPORE))
        if requested_week_end_date is not None else None
    )

    try:
        campaign = _resolve_campaign(campaign_query, selected_id, scope)
        counts = repository.get_campaign_member_metrics(
            scope, campaign.campaign_id, now, week_start, last_week_start,
            requested_start, requested_end,
        )
    except CampaignUnavailable as exc:
        return _error("campaign_unavailable", str(exc))
    except CampaignAmbiguous as exc:
        return _error("campaign_ambiguous", str(exc))
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    members = counts["campaign_members_total"]
    emailed = counts["clients_emailed_total"]
    sends = int(counts["email_sends_total"])
    coverage = round(100 * emailed / members, 1) if members else None
    state, state_words = _state(campaign, today)
    date_words = f"{today.day} {today:%B %Y}"
    base = (f"{campaign.name} {state_words}. As of {date_words}, "
            f"{members} campaign members; {emailed} have at least one recorded "
            f"email, with {sends} recorded email sends.")
    if query.period == "specific_week":
        weekly = (f"{counts['members_added_requested_week']} members were added "
                  f"during the week of {requested_week_start_date.day} "
                  f"{requested_week_start_date:%B %Y} to "
                  f"{requested_week_end_date.day} {requested_week_end_date:%B %Y}.")
    elif query.period == "last_week":
        weekly = (f"{counts['members_added_last_week']} members were added last week "
                  f"({last_week_start_date.day} {last_week_start_date:%B %Y} to "
                  f"{last_week_end_date.day} {last_week_end_date:%B %Y}).")
    else:
        weekly = f"{counts['members_added_this_week']} members were added this week."
    summary = (f"{base} {weekly} The number of clients contacted in that week "
               "is unavailable because campaign_member has no contact-event history.")
    result = {
        "data_source": "synthetic",
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.name,
        "campaign_status": campaign.status,
        "reporting_state": state,
        "campaign_start_date": (campaign.start_date.isoformat()
                                if campaign.start_date is not None else None),
        "campaign_end_date": (campaign.end_date.isoformat()
                              if campaign.end_date is not None else None),
        "as_of_date": today.isoformat(),
        "as_of_time": now.isoformat(),
        "requested_period": query.period,
        "week_start_date": week_start_date.isoformat(),
        "last_week_start_date": last_week_start_date.isoformat(),
        "last_week_end_date": last_week_end_date.isoformat(),
        "campaign_members_total": members,
        "clients_emailed_total": emailed,
        "email_sends_total": sends,
        "email_coverage_percent": coverage,
        "members_added_this_week": counts["members_added_this_week"],
        "members_added_last_week": counts["members_added_last_week"],
        "contact_history_available": False,
        "weekly_email_history_available": False,
        "summary": summary,
        "metric_definition": (
            "Active campaign members added by this adviser are counted once. "
            "Clients emailed means members whose stored email_send_count is greater "
            "than zero; email_sends_total sums that stored field. These are cumulative "
            "snapshot values, not proof of delivery or counts of all contact channels. "
            "Member additions use Monday-Sunday Singapore weeks. No per-send or "
            "per-contact timestamps are available from campaign_member."
        ),
    }
    if requested_week_date is not None:
        result.update({
            "week_of": requested_week_date.isoformat(),
            "requested_week_start_date": requested_week_start_date.isoformat(),
            "requested_week_end_date": requested_week_end_date.isoformat(),
            "members_added_requested_week": counts["members_added_requested_week"],
        })
    return result


def execute_contact_ranking(arguments: dict, metadata: dict | None) -> dict:
    """Rank adviser-owned campaigns by cumulative email reach or member growth."""
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
    if query.metric == "clients_emailed" and query.period != "campaign_to_date":
        return _error(
            "period_unavailable",
            "Weekly email reach is unavailable because campaign_member stores an "
            "email count without a per-send date. Ask for campaign-to-date email "
            "reach or rank members added in a week.",
        )

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
        rows = repository.rank_campaigns_by_member_metric(
            scope, query.metric, period_start, period_end, now
        )
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    campaign_count = rows[0]["campaign_count"] if rows else 0
    visible = rows[:20]
    ranking = [{
        "campaign_id": str(row["campaign_id"]),
        "campaign_name": row["name"],
        "campaign_status": row["status"],
        "campaign_members_total": row["campaign_members_total"],
        "clients_emailed_total": row["clients_emailed"],
        "members_added_in_period": row["members_added"],
        "metric_count": row["count_value"],
    } for row in visible]
    highest = ranking[0]["metric_count"] if ranking else 0
    leaders = [row for row in ranking if row["metric_count"] == highest]
    leaders_truncated = bool(rows and rows[0]["tie_count"] > len(leaders))
    label = "clients with a recorded email" if query.metric == "clients_emailed" else "members added"
    if not ranking:
        summary = "No campaigns are available to this adviser."
    elif highest == 0:
        summary = f"No available campaign has recorded {label} {period_words}."
    elif leaders_truncated:
        summary = (f"At least {len(leaders)} campaigns tie for the most {label} "
                   f"{period_words}: {highest} each. The full tie is truncated.")
    elif len(leaders) == 1:
        summary = (f"{leaders[0]['campaign_name']} has the most {label} "
                   f"{period_words}: {highest}.")
    else:
        names = ", ".join(row["campaign_name"] for row in leaders)
        summary = f"{names} tie for the most {label} {period_words}: {highest} each."
    return {
        "data_source": "synthetic",
        "metric": query.metric,
        "requested_period": query.period,
        "period_start_date": period_start.date().isoformat() if period_start else None,
        "period_end_date": period_end_date.isoformat(),
        "as_of_time": now.isoformat(),
        "campaign_count": campaign_count,
        "ranking_truncated": campaign_count > len(ranking),
        "leaders_truncated": leaders_truncated,
        "ranked_campaigns": ranking,
        "leaders": leaders,
        "highest_count": highest,
        "contact_history_available": False,
        "summary": summary,
        "metric_definition": (
            "Only active members added by this adviser to adviser-owned campaigns "
            "are included. clients_emailed counts members with email_send_count > 0 "
            "as a cumulative snapshot. members_added counts member rows created in "
            "the requested Singapore-time period. These metrics do not count all "
            "forms of client contact or prove email delivery."
        ),
    }

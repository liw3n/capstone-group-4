"""Render read-only campaign performance tool results without an LLM round-trip."""

from datetime import date, timedelta
from html import escape
from typing import Any


def _text(value: object) -> str:
    # Campaign names are stored data, not trusted Markdown. Escape them before
    # placing them in a table or bold text so they cannot alter the answer.
    result = escape(str(value).replace("\r", " ").replace("\n", " "), quote=False)
    for character in ("\\", "`", "*", "_", "[", "]", "|"):
        result = result.replace(character, "\\" + character)
    return result


def _date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {parsed:%b %Y}"


def _count(payload: dict[str, Any], key: str) -> int:
    value = payload[key]
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {key}")
    return value


def _coverage(payload: dict[str, Any], members: int) -> str:
    value = payload["email_coverage_percent"]
    if value is None and members == 0:
        return "N/A (no members)"
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 100
    ):
        return f"{value:g}%"
    raise ValueError("Invalid email coverage")


def render_performance_result(payload: dict[str, Any], view: str) -> str:
    """Present only metrics recorded in the scoped campaign-member result."""
    if payload.get("data_source") != "synthetic" or "error_code" in payload:
        raise ValueError("Invalid campaign performance result")
    name = _text(payload["campaign_name"])
    if view == "week_added":
        if payload["requested_period"] != "specific_week":
            raise ValueError("Missing requested week")
        start = _date(payload["requested_week_start_date"])
        end = _date(payload["requested_week_end_date"])
        count = _count(payload, "members_added_requested_week")
        return (
            f"In the week **{start}–{end}**, **{count} members** were added "
            f"to **{name}**.\n\n"
            "*This measures campaign membership, not client contact. "
            "Figures are synthetic.*"
        )
    as_of = _date(payload["as_of_date"])
    if view == "members":
        count = _count(payload, "campaign_members_total")
        return f"As of {as_of}, **{name}** has **{count} campaign members**. *Synthetic records.*"
    if view == "emailed":
        emailed = _count(payload, "clients_emailed_total")
        members = _count(payload, "campaign_members_total")
        return (
            f"As of {as_of}, **{emailed} of {members} members** of **{name}** "
            "have at least one recorded email. *Recorded emails do not confirm "
            "delivery or replies; figures are synthetic.*"
        )
    if view == "sends":
        sends = _count(payload, "email_sends_total")
        return (
            f"As of {as_of}, **{name}** has **{sends} recorded email sends**. "
            "*This is a cumulative synthetic count, not proof of delivery.*"
        )
    if view == "coverage":
        members = _count(payload, "campaign_members_total")
        emailed = _count(payload, "clients_emailed_total")
        coverage = _coverage(payload, members)
        return (
            f"Email coverage for **{name}** is **{coverage}** as of {as_of} "
            f"({emailed} of {members} members have a recorded email). "
            "*This does not confirm delivery; figures are synthetic.*"
        )
    if view in {"this_week_added", "last_week_added", "compare_weeks"}:
        expected_period = "last_week" if view == "last_week_added" else "this_week"
        if payload["requested_period"] != expected_period:
            raise ValueError("Unexpected member-addition period")
        this_week = _count(payload, "members_added_this_week")
        last_week = _count(payload, "members_added_last_week")
        this_start = _date(payload["week_start_date"])
        last_start = _date(payload["last_week_start_date"])
        last_end = _date(payload["last_week_end_date"])
        if view == "this_week_added":
            return (
                f"**{this_week} members** were added to **{name}** so far this "
                f"week (from {this_start}, as of {as_of}). "
                "*This is membership, not client contact; figures are synthetic.*"
            )
        if view == "last_week_added":
            return (
                f"**{last_week} members** were added to **{name}** last week "
                f"({last_start}–{last_end}). "
                "*This is membership, not client contact; figures are synthetic.*"
            )
        if this_week == last_week:
            trend = f"The count stayed the same at {this_week} in both weeks."
        else:
            direction = "increased" if this_week > last_week else "decreased"
            trend = f"The count {direction} by {abs(this_week - last_week)}."
        return (
            f"For **{name}**, **{this_week} members** were added this week "
            f"(from {this_start}, as of {as_of}), versus **{last_week}** last week "
            f"({last_start}–{last_end}). {trend} "
            "*These are synthetic member additions, not client contacts.*"
        )
    if view != "summary":
        raise ValueError("Unsupported performance view")

    members = _count(payload, "campaign_members_total")
    emailed = _count(payload, "clients_emailed_total")
    sends = _count(payload, "email_sends_total")
    coverage_text = _coverage(payload, members)
    state = payload["reporting_state"]
    if state not in {"draft", "upcoming", "ongoing", "paused", "completed"}:
        raise ValueError("Invalid campaign state")
    week_start = date.fromisoformat(payload["week_start_date"])
    last_start = payload["last_week_start_date"]
    last_end = payload["last_week_end_date"]
    return "\n".join((
        f"**{name} — performance as of {_date(payload['as_of_date'])}**",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Campaign status | {state.title()} |",
        f"| Campaign members | {members} |",
        f"| Members with a recorded email | {emailed} |",
        f"| Total recorded email sends | {sends} |",
        f"| Email coverage | {coverage_text} |",
        f"| Members added this week ({_date(week_start.isoformat())}–"
        f"{_date((week_start + timedelta(days=6)).isoformat())}) | "
        f"{_count(payload, 'members_added_this_week')} |",
        f"| Members added last week ({_date(last_start)}–{_date(last_end)}) | "
        f"{_count(payload, 'members_added_last_week')} |",
        "",
        "*Figures are synthetic. A recorded email does not confirm delivery "
        "or a reply.*",
    ))


def render_ranking_result(payload: dict[str, Any]) -> str:
    """Show every visible leader, including ties, without inventing contacts."""
    if payload.get("data_source") != "synthetic" or "error_code" in payload:
        raise ValueError("Invalid campaign ranking result")
    metric = payload["metric"]
    period = payload["requested_period"]
    if metric == "email_coverage" and period == "campaign_to_date":
        direction = payload["direction"]
        if direction not in {"most", "least"}:
            raise ValueError("Invalid campaign ranking direction")
        leaders = payload["leaders"]
        if not isinstance(leaders, list):
            raise ValueError("Invalid campaign leaders")
        if _count(payload, "campaign_count") == 0:
            return ("No adviser-owned campaign with members is available for an email "
                    "coverage comparison. *Synthetic records.*")
        title = f"{'Highest' if direction == 'most' else 'Lowest'} email coverage"
        lines = [
            f"**{title} (as of {_date(payload['period_end_date'])})**",
            "",
            "| Campaign | Email coverage |",
            "| --- | ---: |",
        ]
        for leader in leaders:
            if not isinstance(leader, dict):
                raise ValueError("Invalid campaign leader")
            members = _count(leader, "campaign_members_total")
            emailed = _count(leader, "clients_emailed_total")
            if members == 0 or emailed > members:
                raise ValueError("Invalid campaign coverage")
            lines.append(
                f"| {_text(leader['campaign_name'])} | "
                f"{_coverage(leader, members)} ({emailed}/{members} members) |"
            )
        if payload.get("leaders_truncated"):
            lines.extend(("", "Additional tied campaigns are not shown."))
        lines.extend((
            "",
            "*Figures are synthetic. Campaigns with no members are excluded. "
            "A recorded email does not confirm delivery or replies.*",
        ))
        return "\n".join(lines)
    if metric == "clients_emailed" and period == "campaign_to_date":
        title = "Most members with a recorded email"
        column = "Members with a recorded email"
        timing = f"as of {_date(payload['period_end_date'])}"
    elif metric == "members_added" and period in {"this_week", "last_week"}:
        title = "Most members added"
        column = "Members added"
        timing = f"{_date(payload['period_start_date'])}–{_date(payload['period_end_date'])}"
    else:
        raise ValueError("Unsupported ranking metric or period")
    leaders = payload["leaders"]
    highest = _count(payload, "highest_count")
    if not isinstance(leaders, list):
        raise ValueError("Invalid campaign leaders")
    if _count(payload, "campaign_count") == 0:
        return "No campaigns are available to this adviser. *Synthetic records.*"
    if highest == 0:
        return f"**{title} ({timing})**\n\nNo campaign has a recorded count above zero. *Synthetic records.*"
    lines = [
        f"**{title} ({timing})**",
        "",
        f"| Campaign | {column} |",
        "| --- | ---: |",
    ]
    for leader in leaders:
        if not isinstance(leader, dict) or _count(leader, "metric_count") != highest:
            raise ValueError("Invalid campaign leader")
        lines.append(f"| {_text(leader['campaign_name'])} | {highest} |")
    if payload.get("leaders_truncated"):
        lines.extend(("", "Additional tied campaigns are not shown."))
    lines.extend((
        "",
        "*Figures are synthetic. Recorded emails do not confirm delivery or replies.*"
        if metric == "clients_emailed" else "*Figures are synthetic member additions.*",
    ))
    return "\n".join(lines)


def render_performance_error(payload: dict[str, Any]) -> str:
    """Return a safe explanation without a second model request."""
    code = payload.get("error_code")
    if code == "campaign_unavailable":
        return "I couldn't find that campaign among those available to you. Please check its name."
    if code == "campaign_ambiguous":
        return "More than one available campaign has that name. Please provide its campaign ID."
    if code == "storage_unavailable":
        return "The campaign database is temporarily unavailable. Please try again."
    if code == "future_period":
        return "The requested week has not started yet."
    if code in {"invalid_arguments", "missing_campaign", "invalid_campaign_context"}:
        return "Please check the campaign name and requested week, then try again."
    return "I couldn't retrieve the campaign performance right now. Please try again."

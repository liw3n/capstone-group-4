"""Deterministic campaign context recovery for campaign-email chat turns."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Protocol

from app.campaigns import clock
from app.campaigns.repository import RequestScope, list_active_campaigns


class HistoryItem(Protocol):
    user: bool | str
    message_content: str


_EMAIL_WORKFLOW_REQUEST_PATTERN = re.compile(
    r"(?:\b(?:draft|write|prepare|review|revise|edit|send)\w*\b.{0,80}"
    r"\b(?:e[ -]?mails?|mails?|outreach)\b|"
    r"\b(?:e[ -]?mails?|mails?|outreach)\b.{0,80}"
    r"\b(?:draft|copy|message|preview|recipients?|send|revise|edit)\w*\b|"
    r"\b(?:e[ -]?mail|mail)\s+(?:the\s+)?(?:clients?|contacts?|recipients?)\b)",
    re.IGNORECASE,
)
_UUID_PATTERN = re.compile(
    r"(?<![0-9a-f])"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    r"(?![0-9a-f])",
    re.IGNORECASE,
)
_EXPLICIT_CAMPAIGN_ID_PATTERN = re.compile(
    r"\bcampaign\s+(?:id|identifier)\s*(?::|is)?\s*[a-z0-9][a-z0-9_-]{2,}\b",
    re.IGNORECASE,
)
_SIGNOFF_QUESTION_PATTERN = re.compile(
    r"(?:what|which)\s+(?:name.*sign[ -]?off|sign[ -]?off.*(?:use|name))|"
    r"name.*email.*signed|sign[ -]?off\s+name",
    re.IGNORECASE,
)
_SIGNOFF_COMMAND_PATTERN = re.compile(
    r"\b(?:draft|email|campaign|recipient|subject|message|body|edit|change|send)\b",
    re.IGNORECASE,
)
_ADVISER_TITLE_PATTERN = re.compile(
    r"^(?:financial\s+advis(?:e|o)r|fa)$", re.IGNORECASE
)
_EMAIL_CAMPAIGN_QUESTION_PATTERN = re.compile(
    r"which\s+campaign.*(?:e[ -]?mail|use)|"
    r"campaign\s+e[ -]?mail.*which\s+campaign",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL_PREVIEW_PATTERN = re.compile(
    r"^##\s+Review campaign e[ -]?mail\b", re.IGNORECASE
)
_EMAIL_CONTENT_QUESTION_PATTERN = re.compile(
    r"provide both the e[ -]?mail subject and message|"
    r"provide an e[ -]?mail message",
    re.IGNORECASE,
)
_EMAIL_PREVIEW_REPLY_PATTERN = re.compile(
    r"\b(?:revise|edit|change|update|replace|rewrite|shorten|shorter|longer|"
    r"subject|body|message|recipients?|sign[ -]?off)\b|"
    r"\bmake\s+(?:it|the\s+(?:subject|body|message))\b",
    re.IGNORECASE,
)
_EXPLICIT_EMAIL_CANCEL_PATTERN = re.compile(
    r"\b(?:cancel|exit|stop|discard|abandon)\b.{0,40}"
    r"\b(?:e[ -]?mail|outreach)\b|"
    r"\b(?:e[ -]?mail|outreach)\b.{0,40}"
    r"\b(?:cancel|exit|stop|discard|abandon)\b",
    re.IGNORECASE,
)
_SHORT_CANCEL_PATTERN = re.compile(
    r"^(?:cancel|exit|stop|discard|never\s*mind|forget\s+it)"
    r"(?:\s+(?:this|it|the\s+draft|drafting))?[.! ]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CampaignContextResolution:
    status: str
    campaign_id: str | None = None
    candidates: tuple[str, ...] = ()


def _words(value: str) -> str:
    return " ".join(
        re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold())
    )


def pending_campaign_email_prompt(
    history: Iterable[HistoryItem],
) -> str | None:
    """Return the kind of email input requested by the latest assistant turn."""
    items = tuple(history)
    if not items or items[-1].user is not False:
        return None
    message = items[-1].message_content
    if _SIGNOFF_QUESTION_PATTERN.search(message):
        return "signoff"
    if _EMAIL_CAMPAIGN_QUESTION_PATTERN.search(message):
        return "campaign"
    if _EMAIL_PREVIEW_PATTERN.search(message):
        return "preview"
    if _EMAIL_CONTENT_QUESTION_PATTERN.search(message):
        return "content"
    return None


def is_campaign_email_cancel(
    latest_message: str, history: Iterable[HistoryItem]
) -> bool:
    """Recognise an explicit exit, or a short exit while email input is pending."""
    if _EXPLICIT_EMAIL_CANCEL_PATTERN.search(latest_message):
        return True
    return bool(
        pending_campaign_email_prompt(history)
        and _SHORT_CANCEL_PATTERN.fullmatch(latest_message.strip())
    )


def is_campaign_email_turn(
    latest_message: str, history: Iterable[HistoryItem]
) -> bool:
    """Identify an email request or a bounded reply to a pending email prompt."""
    items = tuple(history)
    if is_campaign_email_cancel(latest_message, items):
        return True
    if _EMAIL_WORKFLOW_REQUEST_PATTERN.search(latest_message):
        return True
    pending = pending_campaign_email_prompt(items)
    if pending in {"campaign", "signoff", "content"}:
        return True
    return pending == "preview" and bool(
        _EMAIL_PREVIEW_REPLY_PATTERN.search(latest_message)
    )


def signoff_reply(
    latest_message: str, history: Iterable[HistoryItem]
) -> str | None:
    """Extract a short adviser answer only after a server sign-off question."""
    items = tuple(history)
    if not (
        items
        and items[-1].user is False
        and _SIGNOFF_QUESTION_PATTERN.search(items[-1].message_content)
    ):
        return None
    lines = [" ".join(line.split()) for line in latest_message.splitlines()]
    lines = [line for line in lines if line and not _ADVISER_TITLE_PATTERN.fullmatch(line)]
    if not lines:
        return None
    candidate = re.sub(
        r"^(?:please\s+)?(?:use|sign(?:\s+it)?\s+(?:as|by))\s+",
        "",
        lines[0],
        flags=re.IGNORECASE,
    ).strip(" .")
    if (
        not candidate
        or len(candidate) > 100
        or not any(character.isalpha() for character in candidate)
        or _SIGNOFF_COMMAND_PATTERN.search(candidate)
    ):
        return None
    return candidate


def resolve_campaign_context(
    history: Iterable[HistoryItem],
    scope: RequestScope,
    *,
    latest_message: str | None = None,
) -> CampaignContextResolution:
    """Resolve a recent accessible campaign by exact name or identifier."""
    campaigns = list_active_campaigns(scope, clock.current_date())
    if not campaigns:
        return CampaignContextResolution("none")
    messages = [item.message_content for item in history if item.user is not False]
    if latest_message:
        messages.append(latest_message)
    for content in reversed(messages):
        message = f" {_words(content)} "
        matches = {
            campaign.campaign_id: campaign.name
            for campaign in campaigns
            if f" {_words(campaign.name)} " in message
            or f" {_words(campaign.campaign_id)} " in message
        }
        if len(matches) > 1:
            return CampaignContextResolution(
                "ambiguous", candidates=tuple(sorted(matches.values()))
            )
        if len(matches) == 1:
            return CampaignContextResolution("matched", next(iter(matches)))
        if _UUID_PATTERN.search(content) or _EXPLICIT_CAMPAIGN_ID_PATTERN.search(content):
            return CampaignContextResolution("not_found")
    return CampaignContextResolution("none")


def recent_campaign_id(
    history: Iterable[HistoryItem],
    scope: RequestScope,
    *,
    latest_message: str | None = None,
) -> str | None:
    resolution = resolve_campaign_context(
        history, scope, latest_message=latest_message
    )
    return resolution.campaign_id if resolution.status == "matched" else None

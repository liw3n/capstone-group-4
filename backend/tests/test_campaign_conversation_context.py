from types import SimpleNamespace

import pytest

from app.campaigns import conversation_context
from app.campaigns.repository import RequestScope
from app.store import ChatHistoryItem


def campaigns():
    return (
        SimpleNamespace(campaign_id="campaign-1", name="First Home Starter Bundle"),
        SimpleNamespace(campaign_id="campaign-2", name="Legacy Protection Refresh"),
    )


def test_latest_unique_campaign_name_is_reused(monkeypatch):
    monkeypatch.setattr(conversation_context, "list_active_campaigns", lambda *_: campaigns())
    history = [
        ChatHistoryItem("2026-11-01T00:00:00Z", "fa-1", "Use First Home Starter Bundle"),
        ChatHistoryItem("2026-11-01T00:01:00Z", False, "What should I draft?"),
    ]
    assert conversation_context.recent_campaign_id(
        history, RequestScope("fa-1")
    ) == "campaign-1"


def test_latest_campaign_name_overrides_older_context(monkeypatch):
    monkeypatch.setattr(conversation_context, "list_active_campaigns", lambda *_: campaigns())
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", "fa-1", "Use Legacy Protection Refresh"
    )]
    assert conversation_context.recent_campaign_id(
        history,
        RequestScope("fa-1"),
        latest_message="Draft an email for First Home Starter Bundle",
    ) == "campaign-1"


def test_ambiguous_campaign_message_is_not_guessed(monkeypatch):
    monkeypatch.setattr(conversation_context, "list_active_campaigns", lambda *_: campaigns())
    resolution = conversation_context.resolve_campaign_context(
        [ChatHistoryItem(
            "2026-11-01T00:00:00Z", "fa-1",
            "Compare First Home Starter Bundle and Legacy Protection Refresh",
        )],
        RequestScope("fa-1"),
    )
    assert resolution.status == "ambiguous"
    assert resolution.campaign_id is None


def test_short_reply_after_email_prompt_keeps_email_context():
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "Which sign-off should I use for this email?",
    )]
    assert conversation_context.is_campaign_email_turn("Stephen", history) is True
    assert conversation_context.is_campaign_email_turn("Hello", []) is False


def test_plural_email_request_uses_email_context():
    assert conversation_context.is_campaign_email_turn(
        "Draft emails for clients", []
    ) is True


@pytest.mark.parametrize("message", [
    "What proportion of Legacy Protection Refresh members have at least one recorded email send?",
    "Show me how membership additions for Legacy Protection Refresh changed between last week and this week.",
    "Which campaign has the lowest email coverage?",
    "How many email sends are recorded for Legacy Protection Refresh?",
])
def test_performance_question_does_not_enter_email_drafting(message):
    pending_signoff = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "What name would you like me to use in the email sign-off?",
    )]
    assert conversation_context.is_campaign_email_turn(message, []) is False
    assert conversation_context.is_campaign_email_turn(message, pending_signoff) is False


def test_explicit_email_request_with_member_metric_still_enters_drafting():
    assert conversation_context.is_campaign_email_turn(
        "Draft an email to members added last week", []
    ) is True
    assert conversation_context.is_campaign_email_turn(
        "Can you show me a draft email to members added last week?", []
    ) is True
    assert conversation_context.is_campaign_email_turn(
        "Show me the email send preview", []
    ) is True


def test_pending_email_can_be_cancelled_with_a_short_reply():
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "What name would you like me to use in the email sign-off?",
    )]
    assert conversation_context.is_campaign_email_cancel("Never mind", history) is True
    assert conversation_context.is_campaign_email_turn("Never mind", history) is True


def test_preview_accepts_edits_but_not_unrelated_tool_requests():
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "## Review campaign email\n\nReview the subject and recipients.",
    )]
    assert conversation_context.is_campaign_email_turn(
        "Make the subject shorter", history
    ) is True
    assert conversation_context.is_campaign_email_turn(
        "Add that the session includes an educational discussion", history
    ) is True
    assert conversation_context.is_campaign_email_turn(
        "Show campaign performance", history
    ) is False


def test_preview_general_approval_requires_preview_context():
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "## Review campaign email\n\nReview the subject and recipients.",
    )]
    assert conversation_context.is_campaign_email_general_approval(
        "Looks good, send it", history
    ) is True
    assert conversation_context.is_campaign_email_general_approval(
        "Proceed", history
    ) is True
    assert conversation_context.is_campaign_email_general_approval(
        "Looks good, send it", []
    ) is False


@pytest.mark.parametrize(
    "assistant_message",
    [
        "## Campaign email result\n\n**Status:** sent",
        "## Email drafting ended\n\nNo email was sent.",
    ],
)
def test_terminal_email_response_releases_other_tools(assistant_message):
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False, assistant_message,
    )]
    assert conversation_context.is_campaign_email_turn(
        "Show active campaigns", history
    ) is False
    assert conversation_context.is_campaign_email_turn(
        "Show email performance by campaign", history
    ) is False


def test_short_signoff_reply_is_extracted_without_the_adviser_title():
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "What name would you like me to use in the email sign-off?",
    )]
    assert conversation_context.signoff_reply(
        "Steven\nFinancial Advisor", history
    ) == "Steven"


def test_non_name_reply_is_not_treated_as_a_signoff():
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "What name would you like me to use in the email sign-off?",
    )]
    assert conversation_context.signoff_reply(
        "Draft the email for me", history
    ) is None


def test_campaign_id_in_latest_message_is_accepted(monkeypatch):
    monkeypatch.setattr(conversation_context, "list_active_campaigns", lambda *_: campaigns())
    resolution = conversation_context.resolve_campaign_context(
        [], RequestScope("fa-1"), latest_message="Draft email for campaign-2"
    )
    assert resolution.status == "matched"
    assert resolution.campaign_id == "campaign-2"


def test_unknown_explicit_id_does_not_reuse_older_campaign(monkeypatch):
    monkeypatch.setattr(conversation_context, "list_active_campaigns", lambda *_: campaigns())
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", "fa-1", "Use First Home Starter Bundle"
    )]
    resolution = conversation_context.resolve_campaign_context(
        history, RequestScope("fa-1"),
        latest_message="Draft an email for campaign ID c12345",
    )
    assert resolution.status == "not_found"
    assert resolution.campaign_id is None

"""Straightforward performance questions bypass the general model tool loop."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.campaigns.repository import RequestScope
from app.config import Settings
from app.llm.orchestrator import ChatOrchestrator


class NoModelCalls:
    def create_chat_completion(self, *_args, **_kwargs):
        raise AssertionError("A direct performance answer must not call the model")

    def create_structured_completion(self, *_args, **_kwargs):
        raise AssertionError("A direct performance answer must not call the model")


class RecordingRegistry:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.scope = None

    def bind_scope(self, scope, campaign_id=None, session_id=None,
                   latest_user_message=None):
        self.scope = scope
        return self

    def execute(self, name, arguments):
        self.calls.append((name, json.loads(arguments)))
        return json.dumps(self.response)

    def schemas(self):
        raise AssertionError("The fast path must not fetch all MCP tool schemas")


def orchestrator(response):
    registry = RecordingRegistry(response)
    settings = Settings(_env_file=None, groq_api_key="test-key")
    return ChatOrchestrator(NoModelCalls(), settings, registry), registry


def performance_payload(name="Custom High-Net-Worth Advisory Outreach"):
    return {
        "data_source": "synthetic",
        "campaign_name": name,
        "reporting_state": "ongoing",
        "as_of_date": "2026-11-08",
        "requested_period": "this_week",
        "campaign_members_total": 8,
        "clients_emailed_total": 6,
        "email_sends_total": 8,
        "email_coverage_percent": 75.0,
        "week_start_date": "2026-11-02",
        "last_week_start_date": "2026-10-26",
        "last_week_end_date": "2026-11-01",
        "members_added_this_week": 0,
        "members_added_last_week": 2,
    }


def test_summary_calls_scoped_mcp_tool_without_model_or_schema_lookup():
    app, registry = orchestrator(performance_payload())
    result = app.run(
        "Give me a performance summary for Custom High-Net-Worth Advisory Outreach, "
        "including its email coverage.",
        [], scope=RequestScope("adv-demo"),
    )

    assert registry.scope.fa_id == "adv-demo"
    assert registry.calls == [
        ("get_campaign_contact_performance", {
            "campaign": "Custom High-Net-Worth Advisory Outreach",
            "period": "this_week",
        }),
    ]
    assert "75%" in result.answer
    assert "8" in result.answer and "6" in result.answer
    assert "Key Points" not in result.answer and "Notes" not in result.answer


@pytest.mark.parametrize("question,view_text,period", [
    ("How many members are in First Home Starter Bundle?", "8 campaign members", "this_week"),
    ("How many members of First Home Starter Bundle have a recorded email send?",
     "6 of 8 members", "this_week"),
    ("How many email sends are recorded for First Home Starter Bundle?",
     "8 recorded email sends", "this_week"),
    ("What percentage of First Home Starter Bundle members have a recorded email?",
     "75%", "this_week"),
    ("How many members were added to First Home Starter Bundle this week?",
     "0 members", "this_week"),
    ("How many members were added to First Home Starter Bundle last week?",
     "2 members", "last_week"),
    ("Compare this week's and last week's member additions for First Home Starter Bundle.",
     "decreased by 2", "this_week"),
])
def test_other_straightforward_metrics_are_fast(question, view_text, period):
    response = performance_payload("First Home Starter Bundle")
    response["requested_period"] = period
    app, registry = orchestrator(response)
    result = app.run(question, [], scope=RequestScope("adv-demo"))

    assert registry.calls == [
        ("get_campaign_contact_performance", {
            "campaign": "First Home Starter Bundle", "period": period,
        }),
    ]
    assert view_text in result.answer


@pytest.mark.parametrize("question", [
    '"What percentage of First Home Starter Bundle members have a recorded email?"',
    'What percentage of First Home Starter Bundle members have a recorded email?”',
])
def test_quoted_coverage_question_uses_plain_text_answer(question):
    response = performance_payload("First Home Starter Bundle")
    response.update({
        "campaign_members_total": 13,
        "clients_emailed_total": 11,
        "email_coverage_percent": 84.6,
    })
    app, registry = orchestrator(response)

    result = app.run(question, [], scope=RequestScope("adv-demo"))

    assert registry.calls == [
        ("get_campaign_contact_performance", {
            "campaign": "First Home Starter Bundle", "period": "this_week",
        }),
    ]
    assert "**84.6%**" in result.answer
    assert "11 of 13 members" in result.answer
    assert "\\frac" not in result.answer


@pytest.mark.parametrize("asked_date,expected_iso", [
    ("8 October 2026", "2026-10-08"),
    ("7 September 2026", "2026-09-07"),
])
def test_named_week_is_dynamic_and_counts_member_additions(asked_date, expected_iso):
    response = performance_payload("First Home Starter Bundle")
    selected = date.fromisoformat(expected_iso)
    start = selected - timedelta(days=selected.weekday())
    response.update({
        "requested_period": "specific_week",
        "requested_week_start_date": start.isoformat(),
        "requested_week_end_date": (start + timedelta(days=6)).isoformat(),
        "members_added_requested_week": 4,
    })
    app, registry = orchestrator(response)
    result = app.run(
        f"How many members were added to First Home Starter Bundle "
        f"in the week containing {asked_date}?",
        [], scope=RequestScope("adv-demo"),
    )

    assert registry.calls == [
        ("get_campaign_contact_performance", {
            "campaign": "First Home Starter Bundle",
            "period": "specific_week",
            "week_of": expected_iso,
        }),
    ]
    assert "4 members" in result.answer
    assert "not client contact" in result.answer
    assert str(start.day) in result.answer


def test_ranking_shows_ties_without_model_call():
    app, registry = orchestrator({
        "data_source": "synthetic",
        "metric": "clients_emailed",
        "requested_period": "campaign_to_date",
        "period_end_date": "2026-11-08",
        "campaign_count": 3,
        "highest_count": 11,
        "leaders": [
            {"campaign_name": "First Home Starter Bundle", "metric_count": 11},
            {"campaign_name": "Legacy Protection Refresh", "metric_count": 11},
        ],
        "leaders_truncated": False,
    })
    result = app.run(
        "Which campaign has the most members with a recorded email?",
        [], scope=RequestScope("adv-demo"),
    )

    assert registry.calls == [
        ("get_campaign_contact_ranking", {
            "metric": "clients_emailed", "period": "campaign_to_date",
        }),
    ]
    assert "First Home Starter Bundle" in result.answer
    assert "Legacy Protection Refresh" in result.answer
    assert result.answer.count("| 11 |") == 2


@pytest.mark.parametrize("question,direction,heading", [
    ("Which campaign has the highest email coverage?", "most", "Highest email coverage"),
    ("Which campaign has the least email coverage?", "least", "Lowest email coverage"),
])
def test_email_coverage_ranking_uses_fast_path_and_shows_ties(question, direction, heading):
    app, registry = orchestrator({
        "data_source": "synthetic",
        "metric": "email_coverage",
        "direction": direction,
        "requested_period": "campaign_to_date",
        "period_end_date": "2026-11-08",
        "campaign_count": 2,
        "leaders": [
            {"campaign_name": "First Home Starter Bundle", "campaign_members_total": 4,
             "clients_emailed_total": 2, "email_coverage_percent": 50.0},
            {"campaign_name": "Legacy Protection Refresh", "campaign_members_total": 8,
             "clients_emailed_total": 4, "email_coverage_percent": 50.0},
        ],
        "leaders_truncated": False,
    })
    result = app.run(question, [], scope=RequestScope("adv-demo"))

    assert registry.calls == [("get_campaign_contact_ranking", {
        "metric": "email_coverage", "period": "campaign_to_date", "direction": direction,
    })]
    assert heading in result.answer
    assert "First Home Starter Bundle" in result.answer
    assert "Legacy Protection Refresh" in result.answer
    assert "50% (2/4 members)" in result.answer
    assert "50% (4/8 members)" in result.answer
    assert "does not confirm delivery" in result.answer


def test_empty_email_coverage_ranking_explains_undefined_percentage():
    app, _registry = orchestrator({
        "data_source": "synthetic", "metric": "email_coverage",
        "direction": "least", "requested_period": "campaign_to_date",
        "campaign_count": 0, "leaders": [],
    })
    result = app.run("Which campaign has the lowest email coverage?", [],
                     scope=RequestScope("adv-demo"))
    assert "campaign with members" in result.answer


def test_last_week_ranking_uses_singapore_week_from_tool():
    app, registry = orchestrator({
        "data_source": "synthetic",
        "metric": "members_added",
        "requested_period": "last_week",
        "period_start_date": "2026-10-26",
        "period_end_date": "2026-11-01",
        "campaign_count": 3,
        "highest_count": 4,
        "leaders": [
            {"campaign_name": "First Home Starter Bundle", "metric_count": 4},
        ],
        "leaders_truncated": False,
    })
    result = app.run(
        "Which campaign added the most members last week?",
        [], scope=RequestScope("adv-demo"),
    )
    assert registry.calls == [
        ("get_campaign_contact_ranking", {
            "metric": "members_added", "period": "last_week",
        }),
    ]
    assert "26 Oct 2026–1 Nov 2026" in result.answer
    assert "First Home Starter Bundle" in result.answer


def test_unavailable_campaign_has_safe_error_without_model_call():
    app, _registry = orchestrator({
        "data_source": "synthetic",
        "error_code": "campaign_unavailable",
        "error": "Campaign not found or unavailable to this adviser",
    })
    result = app.run(
        "Give me a performance summary for Unknown Campaign.",
        [], scope=RequestScope("adv-demo"),
    )
    assert "among those available to you" in result.answer
    assert "another adviser" not in result.answer


def test_compound_question_keeps_the_normal_chat_path():
    registry = RecordingRegistry(performance_payload())
    registry.schemas = lambda: []

    class AnsweringModel:
        def create_chat_completion(self, *_args, **_kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="Handled by the normal chat flow", tool_calls=[]
            ))])

    app = ChatOrchestrator(
        AnsweringModel(), Settings(_env_file=None, groq_api_key="test-key"), registry
    )
    result = app.run(
        "Give me a performance summary for Legacy Protection Refresh, "
        "and recommend clients for follow-up.",
        [], scope=RequestScope("adv-demo"),
    )

    assert result.answer == "Handled by the normal chat flow"
    assert registry.calls == []

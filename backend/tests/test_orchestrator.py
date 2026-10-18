import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings
from app.campaigns.clarification import (
    CampaignClarification,
    CampaignIntentExtraction,
    assess_campaign_objective,
)
from app.campaigns.repository import RequestScope
from app.campaigns.models import (
    CampaignDraftArtifact,
    PersistedCampaignDraftArtifact,
    PersistedCampaignDraftOptionSet,
    campaign_revision_changed_fields,
)
from app.campaigns.presentation import render_campaign_draft
from app.llm.errors import LLMProviderError, LLMToolLoopError
from app.llm.orchestrator import (
    ChatOrchestrator,
    SYSTEM_PROMPT,
    _is_campaign_generation_request,
    is_campaign_revision_candidate,
    is_campaign_turn_candidate,
)
from app.store import ChatHistoryItem
from app.tools.registry import ToolDefinition, ToolRegistry


class CalculateSumArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float = Field()
    b: float = Field()


def calculate_sum(a: float, b: float) -> float:
    return a + b


def tool_registry():
    return ToolRegistry([
        ToolDefinition(
            name="calculate_sum",
            description="Add two numbers.",
            arguments_model=CalculateSumArguments,
            handler=calculate_sum,
        )
    ])


def message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def completion(message_value):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message_value)],
    )


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create_chat_completion(self, messages, tools):
        self.calls.append({"messages": list(messages), "tools": tools, "structured": False})
        return self.responses.pop(0)

    def create_structured_completion(
        self, messages, schema, schema_name="campaign_draft_generation"
    ):
        self.calls.append({
            "messages": list(messages), "schema": schema, "structured": True,
            "schema_name": schema_name,
        })
        return self.responses.pop(0)


class CampaignGenerationRegistry:
    def __init__(self, artifact):
        self.artifact = artifact
        self.executed = []

    def bind_scope(self, scope, campaign_id=None):
        return self

    def schemas(self):
        draft_properties = {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "clientMessage": {"type": "string"},
            "criteria": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ageGroups": {"type": "array", "items": {"type": "string"}},
                    "genders": {"type": "array", "items": {"type": "string"}},
                    "cashBands": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ageGroups", "genders", "cashBands"],
            },
            "targetDemographicSummary": {"type": "string"},
            "rationale": {"type": "object", "additionalProperties": {"type": "string"}},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "disclaimer": {"type": "string"},
        }
        preparation_parameters = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "referencesUsed": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "referenceId": {"type": "string"},
                            "version": {"type": "integer"},
                        },
                        "required": ["referenceId", "version"],
                    },
                },
                "draft": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": draft_properties,
                    "required": [key for key in draft_properties if key != "assumptions"],
                },
            },
            "required": ["referencesUsed", "draft"],
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "parameters": preparation_parameters if name == "prepare_campaign_draft" else {},
                },
            }
            for name in ("find_campaign_references", "prepare_campaign_draft", "other_tool")
        ]

    def execute(self, name, arguments_json):
        self.executed.append((name, json.loads(arguments_json)))
        if name == "find_campaign_references":
            return json.dumps({
                "type": "campaign_references",
                "retrievalToken": "signed-token-value",
                "references": [],
            })
        if name == "prepare_campaign_draft":
            return json.dumps(self.artifact)
        raise AssertionError(f"Unexpected tool: {name}")


class FakeClarificationStore:
    def __init__(self):
        self.active = None
        self.status = None

    def get_active(self, _scope, _session_id):
        return self.active

    def start(self, _scope, _session_id, objective, pending_question_ids):
        self.active = CampaignClarification(
            clarification_id="clarification-1",
            objective=objective,
            answers=(),
            pending_question_ids=pending_question_ids,
            round_count=0,
        )
        self.status = "active"
        return self.active

    def update(
        self, _scope, _session_id, clarification_id, answers,
        pending_question_ids, round_count, status="active",
    ):
        assert clarification_id == "clarification-1"
        self.status = status
        self.active = None if status != "active" else CampaignClarification(
            clarification_id=clarification_id,
            objective=self.active.objective,
            answers=answers,
            pending_question_ids=pending_question_ids,
            round_count=round_count,
        )


def settings(**overrides):
    values = {
        "groq_api_key": "test-key",
        "llm_max_tool_rounds": 5,
        "llm_history_limit": 50,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def campaign_draft_artifact():
    return {
        "type": "campaign_draft",
        "data_source": "ai_generated",
        "objective": "Encourage clients nearing retirement to review their assets",
        "referencesUsed": [
            {"referenceId": "campaign-pattern-retirement-001", "version": 1}
        ],
        "draft": {
            "name": "Retirement Asset Review",
            "description": "Invite clients to review how their assets are organised.",
            "clientMessage": (
                "This educational invitation is not financial advice.\n"
                "Any next step requires an individual suitability review."
            ),
            "criteria": {
                "ageGroups": ["55to64"],
                "genders": [],
                "cashBands": ["50kTo250k", "250kTo1m"],
            },
            "targetDemographicSummary": "Clients nearing retirement across all genders.",
            "rationale": {
                "ageGroups": "The retirement transition supports this age group.",
                "genders": "The objective is not gender-specific.",
                "cashBands": "Available assets make these bands a review hypothesis.",
            },
            "assumptions": ["Retirement timing must be confirmed."],
            "disclaimer": (
                "Educational information only, not financial advice; suitability "
                "depends on individual circumstances and adviser review."
            ),
        },
        "validation": {
            "schema_valid": True,
            "policy_valid": True,
            "warnings": ["The assumption requires adviser review."],
        },
        "requires_adviser_review": True,
        "created": False,
    }


def persisted_campaign_draft(revision=1, **draft_changes):
    artifact = campaign_draft_artifact()
    artifact["draft"] = artifact["draft"] | draft_changes
    return PersistedCampaignDraftArtifact.model_validate({
        **artifact,
        "draftId": "11111111-1111-4111-8111-111111111111",
        "revision": revision,
        "status": "generated",
        "changedFields": [],
    })


def persisted_name_options(revision=1):
    return PersistedCampaignDraftOptionSet(
        optionSetId="22222222-2222-4222-8222-222222222222",
        draftId="11111111-1111-4111-8111-111111111111",
        baseRevision=revision,
        field="name",
        options=[
            "Campus Capital Lab",
            "First Portfolio Project",
            "Invest Early Studio",
            "Student Wealth Workshop",
            "Youth Wealth Lab",
        ],
        status="pending",
        expiresAt=datetime.now(timezone.utc) + timedelta(minutes=10),
    )


class CampaignRevisionRegistry:
    def __init__(self):
        self.executed = []

    def bind_scope(self, _scope, _campaign_id=None):
        return self

    def schemas(self):
        raise AssertionError("Selective revision must not use generic model tools")

    def execute(self, name, arguments_json):
        assert name == "revise_campaign_draft"
        arguments = json.loads(arguments_json)
        self.executed.append((name, arguments))
        revised = json.loads(json.dumps(arguments["currentDraft"]))
        for field_name, value in arguments["proposedChanges"].items():
            if field_name in {"ageGroups", "genders", "cashBands"}:
                revised["criteria"][field_name] = value
            else:
                revised[field_name] = value
        return json.dumps({
            "type": "campaign_draft_revision",
            "data_source": "ai_generated",
            "objective": arguments["objective"],
            "referencesUsed": arguments["referencesUsed"],
            "draft": revised,
            "previousRevision": arguments["revision"],
            "revision": arguments["revision"] + 1,
            "changedFields": list(campaign_revision_changed_fields(
                tuple(arguments["fields"])
            )),
            "validation": {
                "schema_valid": True,
                "policy_valid": True,
                "warnings": [],
            },
            "requires_adviser_review": True,
            "created": False,
        })


def intent_extraction(**overrides):
    payload = {
        "planningFocus": "unspecified",
        "audienceSpecified": True,
        "ageGroups": [],
        "ageUnrestricted": False,
        "unsupportedAgeCriterion": False,
        "cashBands": [],
        "cashUnrestricted": False,
        "unsupportedCashCriterion": False,
        "genders": [],
        "genderUnrestricted": False,
    }
    payload.update(overrides)
    return completion(message(content=json.dumps(payload)))


def test_intent_extraction_rejects_contradictory_targeting_state():
    payload = json.loads(intent_extraction().choices[0].message.content)
    payload.update({"ageGroups": ["under35"], "ageUnrestricted": True})

    with pytest.raises(ValidationError, match="restricted and unrestricted"):
        CampaignIntentExtraction.model_validate(payload)


def test_returns_plain_model_answer():
    client = FakeClient([completion(message(content="A real answer"))])
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())

    result = orchestrator.run("Hello", [])

    assert result == "A real answer"
    assert client.calls[0]["messages"][-1] == {"role": "user", "content": "Hello"}


def test_executes_tool_and_returns_follow_up_answer():
    client = FakeClient(
        [
            completion(
                message(
                    tool_calls=[tool_call("call-1", "calculate_sum", '{"a": 2, "b": 3}')]
                )
            ),
            completion(message(content="The total is 5.")),
        ]
    )
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())

    result = orchestrator.run("What is two plus three?", [])

    assert result == "The total is 5."
    follow_up_messages = client.calls[1]["messages"]
    assert follow_up_messages[-1]["role"] == "tool"
    assert follow_up_messages[-1]["tool_call_id"] == "call-1"
    assert '"result": 5.0' in follow_up_messages[-1]["content"]


def test_preserves_user_and_assistant_history():
    client = FakeClient([completion(message(content="Next answer"))])
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())
    history = [
        ChatHistoryItem("2026-01-01T00:00:00Z", "fa-1", "Earlier question"),
        ChatHistoryItem("2026-01-01T00:00:01Z", False, "Earlier answer"),
    ]

    orchestrator.run("Next question", history)

    roles = [entry["role"] for entry in client.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_rejects_empty_provider_response():
    client = FakeClient([completion(message())])
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())

    with pytest.raises(LLMProviderError, match="empty answer"):
        orchestrator.run("Hello", [])


def test_stops_after_maximum_tool_rounds():
    repeated_call = completion(
        message(tool_calls=[tool_call("call-1", "calculate_sum", '{"a": 1, "b": 1}')])
    )
    client = FakeClient([repeated_call, repeated_call])
    orchestrator = ChatOrchestrator(
        client,
        settings(llm_max_tool_rounds=2),
        tool_registry(),
    )

    with pytest.raises(LLMToolLoopError, match="round limit"):
        orchestrator.run("Keep calculating", [])


def test_selected_campaign_context_overrides_history_without_mutating_registry():
    from app.campaigns.repository import DEMO_FA, RequestScope

    client = FakeClient([completion(message(content="Use camp-2"))])
    registry = tool_registry()
    orchestrator = ChatOrchestrator(client, settings(), registry)
    history = [ChatHistoryItem("2026-08-25T00:00:00Z", False, "Earlier results for camp-1")]
    orchestrator.run("What about this campaign?", history,
                     scope=RequestScope(DEMO_FA), campaign_id="camp-2")
    assert '"campaign_id": "camp-2"' in client.calls[0]["messages"][0]["content"]
    assert client.calls[0]["messages"][1]["content"] == "Earlier results for camp-1"
    assert orchestrator.registry is registry


def test_campaign_generation_prompt_requires_retrieval_before_preparation():
    retrieval_position = SYSTEM_PROMPT.index("first call find_campaign_references")
    preparation_position = SYSTEM_PROMPT.index("invokes prepare_campaign_draft itself")
    assert retrieval_position < preparation_position
    assert "schema-constrained draft" in SYSTEM_PROMPT
    assert "retained objective and signed\ntoken" in SYSTEM_PROMPT
    assert "does not save or create" in SYSTEM_PROMPT
    assert "Never claim the campaign was created" in SYSTEM_PROMPT


def test_campaign_client_tool_prompt_separates_pre_and_post_contact_intent():
    assert "Before contact" in SYSTEM_PROMPT
    assert "recommend_clients_for_campaign" in SYSTEM_PROMPT
    assert "After contact" in SYSTEM_PROMPT
    assert "campaign_follow_up" in SYSTEM_PROMPT
    assert "If the requested workflow stage" in SYSTEM_PROMPT
    assert "ask whether the adviser wants a pre-contact eligible audience or an" in SYSTEM_PROMPT
    assert "after-contact no-reply list" in SYSTEM_PROMPT
    assert "Explain why each is listed using its follow_up_reason" in SYSTEM_PROMPT
    assert "not a suitability judgment" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "message_value",
    [
        "I want to run a campaign encouraging clients nearing retirement",
        "Create a retirement campaign",
        "Generate a campaign draft for younger clients",
        "Campaign proposal for an educational retirement review",
        "Start a new campaign",
    ],
)
def test_clear_campaign_generation_requests_use_server_pipeline(message_value):
    assert _is_campaign_generation_request(message_value) is True


@pytest.mark.parametrize(
    "message_value",
    [
        "Show active campaigns",
        "Which campaign contacted the most clients?",
        "How did this campaign perform last week?",
    ],
)
def test_campaign_queries_are_not_misrouted_to_generation(message_value):
    assert _is_campaign_generation_request(message_value) is False


def test_existing_draft_name_regeneration_uses_selective_revision_pipeline():
    current = persisted_campaign_draft()
    registry = CampaignRevisionRegistry()
    client = FakeClient([
        completion(message(content=json.dumps({
            "name": "FutureFunders: Student Investing Lab",
        })))
    ])
    orchestrator = ChatOrchestrator(client, settings(), registry)

    result = orchestrator.run(
        "The campaign name is too generic, generate a more unique name for the campaign",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        revision_context_checked=True,
    )

    assert is_campaign_revision_candidate(
        "The campaign name is too generic, generate a more unique name for the campaign"
    )
    assert client.calls[0]["schema_name"] == "campaign_draft_revision"
    assert set(client.calls[0]["schema"]["properties"]) == {"name"}
    assert registry.executed[0][1]["fields"] == ["name"]
    assert registry.executed[0][1]["currentDraft"] == current.draft.model_dump(mode="json")
    assert result.artifacts[0].revision == 2
    assert result.artifacts[0].draft.name == "FutureFunders: Student Investing Lab"
    assert result.artifacts[0].draft.description == current.draft.description


def test_revision_can_change_multiple_fields_in_one_revision():
    current = persisted_campaign_draft(revision=4)
    registry = CampaignRevisionRegistry()
    client = FakeClient([
        completion(message(content=json.dumps({
            "name": "Retirement Compass",
            "description": "A clearer educational retirement review invitation.",
        })))
    ])
    orchestrator = ChatOrchestrator(client, settings(), registry)

    result = orchestrator.run(
        "Rewrite the campaign name and description",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        revision_context_checked=True,
    )

    assert set(client.calls[0]["schema"]["properties"]) == {"name", "description"}
    assert registry.executed[0][1]["revision"] == 4
    assert registry.executed[0][1]["fields"] == ["name", "description"]
    assert result.artifacts[0].previousRevision == 4
    assert result.artifacts[0].revision == 5


def test_declarative_targeting_change_revises_structured_draft_and_dependent_copy():
    current = persisted_campaign_draft(revision=2)
    registry = CampaignRevisionRegistry()
    client = FakeClient([
        completion(message(content=json.dumps({
            "ageGroups": ["under35"],
            "cashBands": ["under50k"],
            "description": "An educational retirement review for male clients aged 65 and above with at least SGD 250k in available cash.",
            "clientMessage": "Review your retirement plans with an adviser. This is educational information, not financial advice, and any next step requires individual suitability review.",
        })))
    ])
    orchestrator = ChatOrchestrator(client, settings(), registry)

    instruction = (
        "the target age should be above 65 years old and cash availability "
        "should be more than 250k"
    )
    result = orchestrator.run(
        instruction,
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        revision_context_checked=True,
    )

    expected_fields = {
        "ageGroups", "cashBands", "description", "clientMessage",
    }
    assert is_campaign_revision_candidate(instruction) is True
    assert client.calls[0]["schema_name"] == "campaign_draft_revision"
    assert set(client.calls[0]["schema"]["properties"]) == expected_fields
    assert set(registry.executed[0][1]["fields"]) == expected_fields
    revision_context = json.loads(client.calls[0]["messages"][1]["content"])
    assert revision_context["authoritativeTargeting"] == {
        "ageGroups": ["65plus"],
        "cashBands": ["250kTo1m", "above1m"],
    }
    assert registry.executed[0][1]["proposedChanges"]["ageGroups"] == ["65plus"]
    assert registry.executed[0][1]["proposedChanges"]["cashBands"] == [
        "250kTo1m", "above1m"
    ]
    assert result.artifacts[0].draft.name == current.draft.name
    assert result.artifacts[0].draft.criteria.ageGroups == ["65plus"]
    assert result.artifacts[0].draft.criteria.cashBands == ["250kTo1m", "above1m"]
    assert result.artifacts[0].revision == 3


def test_compact_targeting_values_use_active_draft_classifier_then_revision():
    current = persisted_campaign_draft()
    registry = CampaignRevisionRegistry()
    client = FakeClient([
        completion(message(content=json.dumps({
            "action": "revise_fields",
            "fields": ["ageGroups"],
            "optionNumber": None,
        }))),
        completion(message(content=json.dumps({
            "ageGroups": ["under35"],
            "cashBands": ["under50k"],
            "description": "An educational retirement review for clients aged 65 and above with SGD 250k or more in cash.",
            "clientMessage": "Review your retirement plans with an adviser. This is educational information, not financial advice, and requires an individual suitability review.",
        }))),
    ])
    orchestrator = ChatOrchestrator(client, settings(), registry)

    result = orchestrator.run(
        "Age 65+, cash 250k and above.",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        revision_context_checked=True,
    )

    assert client.calls[0]["schema_name"] == "campaign_turn_decision"
    assert client.calls[1]["schema_name"] == "campaign_draft_revision"
    assert registry.executed[0][1]["proposedChanges"]["ageGroups"] == ["65plus"]
    assert registry.executed[0][1]["proposedChanges"]["cashBands"] == [
        "250kTo1m", "above1m"
    ]
    assert result.artifacts[0].revision == 2


def test_ordinary_classifier_cannot_return_a_prose_only_pseudo_revision():
    client = FakeClient([
        completion(message(content=json.dumps({
            "action": "ordinary_chat",
            "fields": [],
            "optionNumber": None,
        }))),
        completion(message(content=(
            "## Draft campaign proposal\n\n"
            "Campaign name: Unsaved replacement\n\n"
            "Target criteria: age 65+"
        ))),
    ])
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())

    result = orchestrator.run(
        "Could the age targeting be more tailored?",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=persisted_campaign_draft(),
        revision_context_checked=True,
    )

    assert result.artifacts == ()
    assert "Campaign draft change was not saved" in result.answer
    assert "No draft fields were changed" in result.answer


def test_ambiguous_revision_asks_for_fields_without_a_model_call():
    orchestrator = ChatOrchestrator(
        FakeClient([]), settings(), CampaignRevisionRegistry()
    )

    result = orchestrator.run(
        "Please improve this campaign",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=persisted_campaign_draft(),
        revision_context_checked=True,
    )

    assert "Which campaign fields should I revise" in result
    assert result.artifacts == ()


def test_name_options_are_structured_and_do_not_mutate_the_draft():
    current = persisted_campaign_draft()
    client = FakeClient([
        completion(message(content=json.dumps({
            "options": [
                "Campus Capital Lab",
                "First Portfolio Project",
                "Invest Early Studio",
                "Student Wealth Workshop",
                "Youth Wealth Lab",
            ],
        })))
    ])
    registry = CampaignRevisionRegistry()
    orchestrator = ChatOrchestrator(client, settings(), registry)

    result = orchestrator.run(
        "Can you give me a more unique campaign name?",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        revision_context_checked=True,
    )

    assert client.calls[0]["schema_name"] == "campaign_draft_field_options"
    proposal = result.artifacts[0]
    assert proposal.field == "name"
    assert proposal.baseRevision == 1
    assert proposal.options[4] == "Youth Wealth Lab"
    assert registry.executed == []
    assert "do not change the draft until you select one" in result.answer


@pytest.mark.parametrize(
    "selection_message",
    ["Let's try the fifth option", "The fifth one, please."],
)
def test_numbered_option_selection_revises_only_its_bound_field(selection_message):
    current = persisted_campaign_draft()
    options = persisted_name_options()
    registry = CampaignRevisionRegistry()
    client = FakeClient([])
    orchestrator = ChatOrchestrator(client, settings(), registry)

    result = orchestrator.run(
        selection_message,
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        pending_draft_options=options,
        revision_context_checked=True,
    )

    assert client.calls == []
    assert registry.executed[0][1]["proposedChanges"] == {
        "name": "Youth Wealth Lab"
    }
    assert registry.executed[0][1]["fields"] == ["name"]
    assert result.artifacts[0].draft.name == "Youth Wealth Lab"
    assert result.selected_option_set_id == options.optionSetId
    assert result.selected_option_number == 5
    assert result.requested_revision_fields == ("name",)


def test_full_campaign_request_renders_active_draft_without_restart():
    current = persisted_campaign_draft(name="Youth Wealth Lab")
    client = FakeClient([])
    orchestrator = ChatOrchestrator(
        client, settings(), CampaignRevisionRegistry()
    )

    result = orchestrator.run(
        "Please draft the full campaign",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=current,
        revision_context_checked=True,
    )

    assert client.calls == []
    assert result.artifacts == ()
    assert "Youth Wealth Lab" in result.answer
    assert "Current revision:** 1" in result.answer
    assert "No draft fields were changed" in result.answer


def test_generation_wording_does_not_replace_an_active_draft_implicitly():
    client = FakeClient([])
    orchestrator = ChatOrchestrator(
        client, settings(), CampaignRevisionRegistry()
    )

    result = orchestrator.run(
        "Please create a retirement campaign",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=persisted_campaign_draft(),
        revision_context_checked=True,
    )

    assert client.calls == []
    assert result.artifacts == ()
    assert "explicitly that you want to start a new campaign" in result.answer


def test_model_classifier_cannot_invent_new_draft_intent():
    client = FakeClient([
        completion(message(content=json.dumps({
            "action": "start_new_draft",
            "fields": [],
            "optionNumber": None,
        })))
    ])
    orchestrator = ChatOrchestrator(
        client, settings(), CampaignRevisionRegistry()
    )

    result = orchestrator.run(
        "Can we rethink the draft?",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=persisted_campaign_draft(),
        revision_context_checked=True,
    )

    assert client.calls[0]["schema_name"] == "campaign_turn_decision"
    assert result.artifacts == ()
    assert "explicitly that you want to start a new campaign" in result.answer


def test_active_draft_does_not_intercept_an_unrelated_tool_request():
    client = FakeClient([
        completion(
            message(tool_calls=[tool_call("call-1", "calculate_sum", '{"a": 2, "b": 3}')])
        ),
        completion(message(content="The total is 5.")),
    ])
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())

    result = orchestrator.run(
        "What is two plus three?",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=persisted_campaign_draft(),
        revision_context_checked=True,
    )

    assert result == "The total is 5."
    assert client.calls[0]["structured"] is False
    assert client.calls[0]["tools"][0]["function"]["name"] == "calculate_sum"


@pytest.mark.parametrize(
    "message_value",
    [
        "Show clients above 65 with more than 250k cash",
        "Which male clients match this campaign?",
        "How did this campaign perform last week?",
        "Draft an email for this campaign",
    ],
)
def test_active_draft_preserves_existing_tool_intent_precedence(message_value):
    client = FakeClient([completion(message(content="Ordinary tool answer"))])
    orchestrator = ChatOrchestrator(client, settings(), tool_registry())

    result = orchestrator.run(
        message_value,
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        current_draft=persisted_campaign_draft(),
        revision_context_checked=True,
    )

    assert result == "Ordinary tool answer"
    assert len(client.calls) == 1
    assert client.calls[0]["structured"] is False
    assert "Do not present, rewrite or claim to save a campaign draft" in (
        client.calls[0]["messages"][0]["content"]
    )


@pytest.mark.parametrize(
    "message_value",
    [
        "Which male clients match this campaign?",
        "Show clients contacted by this campaign who have not replied",
        "How did this campaign perform last week?",
        "List active campaigns",
        "Draft an email for this campaign",
    ],
)
def test_existing_campaign_tool_intents_bypass_active_draft_routing(message_value):
    assert is_campaign_turn_candidate(message_value) is False


def test_revision_without_a_stored_draft_does_not_restart_generation():
    orchestrator = ChatOrchestrator(
        FakeClient([]), settings(), CampaignRevisionRegistry()
    )

    result = orchestrator.run(
        "Generate a more unique campaign name",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        revision_context_checked=True,
    )

    assert "No campaign draft is available to revise" in result
    assert result.artifacts == ()


def test_option_request_without_a_stored_draft_does_not_fall_into_generic_chat():
    orchestrator = ChatOrchestrator(
        FakeClient([]), settings(), CampaignRevisionRegistry()
    )

    result = orchestrator.run(
        "Give me five more unique campaign name options",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
        revision_context_checked=True,
    )

    assert "No campaign draft is available to revise" in result
    assert result.artifacts == ()


def test_successful_campaign_draft_is_rendered_without_another_model_call():
    artifact = campaign_draft_artifact()
    client = FakeClient([
        completion(message(content=json.dumps({
            "referencesUsed": artifact["referencesUsed"],
            "draft": artifact["draft"],
        }))),
    ])
    registry = CampaignGenerationRegistry(artifact)
    orchestrator = ChatOrchestrator(client, settings(), registry)

    result = orchestrator.run("Create a retirement campaign", [])

    assert len(client.calls) == 1
    assert client.calls[0]["structured"] is True
    assert [message["role"] for message in client.calls[0]["messages"]] == [
        "system", "user"
    ]
    assert "signed-token-value" not in client.calls[0]["messages"][1]["content"]
    assert "campaign_references" in client.calls[0]["messages"][1]["content"]
    assert "prepare_campaign_draft" not in {
        tool["function"]["name"] for tool in client.calls[0].get("tools", [])
    }
    assert set(client.calls[0]["schema"]["properties"]) == {"referencesUsed", "draft"}
    assert "assumptions" in client.calls[0]["schema"]["properties"]["draft"]["required"]
    assert [name for name, _ in registry.executed] == [
        "find_campaign_references", "prepare_campaign_draft"
    ]
    assert result == render_campaign_draft(CampaignDraftArtifact.model_validate(artifact))
    assert "### Description" in result
    assert artifact["draft"]["description"] in result
    assert "### Client message" in result
    assert "### Disclaimer" in result
    assert "Draft only — not created" in result


def test_vague_life_stage_campaign_requests_clarification_before_retrieval():
    client = FakeClient([intent_extraction()])
    registry = CampaignGenerationRegistry(campaign_draft_artifact())
    clarification_store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        client, settings(), registry, clarification_store=clarification_store
    )

    result = orchestrator.run(
        "Create a campaign targeting students entering the workforce who want "
        "to start planning for their future",
        [],
        scope=RequestScope("fa-1"),
        session_id="session-1",
    )

    assert "What should the campaign primarily cover" in result
    assert "Which supported age group should be used" in result
    assert "No campaign draft has been generated or created yet" in result
    assert len(client.calls) == 1
    assert client.calls[0]["schema_name"] == "campaign_intent_extraction"
    assert registry.executed == []
    assert clarification_store.active.pending_question_ids == ("focus", "age")


def test_clarification_reply_resumes_generation_with_safe_unrestricted_defaults():
    artifact = campaign_draft_artifact()
    client = FakeClient([
        intent_extraction(),
        completion(message(content=json.dumps({
            "referencesUsed": artifact["referencesUsed"],
            "draft": artifact["draft"],
        }))),
    ])
    registry = CampaignGenerationRegistry(artifact)
    clarification_store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        client, settings(), registry, clarification_store=clarification_store
    )
    scope = RequestScope("fa-1")
    orchestrator.run(
        "Create a campaign targeting students entering the workforce who want "
        "to start planning for their future",
        [],
        scope=scope,
        session_id="session-1",
    )

    result = orchestrator.run(
        "Use a general financial planning introduction and target Under 35.",
        [],
        scope=scope,
        session_id="session-1",
    )

    retrieval_arguments = registry.executed[0][1]
    assert "Under 35" in retrieval_arguments["objective"]
    assert "Gender targeting: no gender restriction" in retrieval_arguments["objective"]
    assert "Cash targeting: no cash restriction" in retrieval_arguments["objective"]
    assert clarification_store.status == "completed"
    assert "Draft only — not created" in result


def test_clarified_targeting_is_locked_before_draft_preparation():
    artifact = campaign_draft_artifact()
    generated_draft = artifact["draft"] | {
        "criteria": {
            "ageGroups": ["55to64"],
            "genders": ["female"],
            "cashBands": ["above1m"],
        },
        "targetDemographicSummary": "Male graduates under 35 with no cash restriction.",
        "rationale": {
            "ageGroups": "Under 35 was explicitly selected by the adviser.",
            "genders": "Male graduates were explicitly selected by the adviser.",
            "cashBands": "No cash restriction was requested.",
        },
    }
    client = FakeClient([
        intent_extraction(genders=["male"]),
        completion(message(content=json.dumps({
            "referencesUsed": artifact["referencesUsed"],
            "draft": generated_draft,
        }))),
    ])
    registry = CampaignGenerationRegistry(artifact)
    store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        client, settings(), registry, clarification_store=store
    )
    scope = RequestScope("fa-1")
    orchestrator.run(
        "Create a campaign for male graduates",
        [], scope=scope, session_id="session-1",
    )

    orchestrator.run(
        "Budgeting and emergency savings, under 35.",
        [], scope=scope, session_id="session-1",
    )

    prepared_arguments = registry.executed[1][1]
    assert prepared_arguments["draft"]["criteria"] == {
        "ageGroups": ["under35"],
        "genders": ["male"],
        "cashBands": [],
    }
    generation_prompt = client.calls[1]["messages"][0]["content"]
    assert "targeting criteria are locked by the server" in generation_prompt
    assert '"cashBands":[]' in generation_prompt


def test_latest_explicit_targeting_values_form_the_server_lock():
    assessment = assess_campaign_objective(
        "Create a budgeting campaign for women under 35 with cash below SGD 50,000",
        ("Change the audience to men aged 35-44 with no cash restriction.",),
    )

    assert assessment.question_ids == ()
    assert assessment.targeting_lock.as_payload() == {
        "ageGroups": ["35to44"],
        "genders": ["male"],
        "cashBands": [],
    }


def test_hyphenated_focus_is_understood_but_unsupported_age_is_asked_again():
    client = FakeClient([
        intent_extraction(),
        intent_extraction(
            planningFocus="general_financial_planning",
            ageGroups=["under35"],
        ),
    ])
    store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        client, settings(), CampaignGenerationRegistry(campaign_draft_artifact()),
        clarification_store=store,
    )
    scope = RequestScope("fa-1")
    orchestrator.run(
        "Create a campaign targeting students",
        [], scope=scope, session_id="session-1",
    )

    result = orchestrator.run(
        "1. general financial-planning introduction\n2. Under 30",
        [], scope=scope, session_id="session-1",
    )

    assert "What should the campaign primarily cover" not in result
    assert "Which supported age group should be used" in result
    assert store.active.pending_question_ids == ("age",)


def test_latest_explicit_age_answer_overrides_an_earlier_unsupported_answer():
    objective = "Create a campaign targeting students"
    focus_and_unsupported_age = (
        "General financial-planning introduction for Under 30",
    )

    unresolved = assess_campaign_objective(objective, focus_and_unsupported_age)
    corrected = assess_campaign_objective(
        objective, focus_and_unsupported_age + ("Use the supported Under 35 group",)
    )
    reversed_order = assess_campaign_objective(
        objective,
        ("General financial planning for Under 35", "Change the age to Under 30"),
    )

    assert unresolved.question_ids == ("age",)
    assert corrected.question_ids == ()
    assert reversed_order.question_ids == ("age",)


def test_model_interprets_natural_clarification_then_server_validates_defaults():
    artifact = campaign_draft_artifact()
    client = FakeClient([
        intent_extraction(),
        intent_extraction(planningFocus="general_financial_planning"),
        completion(message(content=json.dumps({
            "referencesUsed": artifact["referencesUsed"],
            "draft": artifact["draft"],
        }))),
    ])
    registry = CampaignGenerationRegistry(artifact)
    store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        client, settings(), registry, clarification_store=store
    )
    scope = RequestScope("fa-1")
    orchestrator.run(
        "Create a campaign targeting students",
        [], scope=scope, session_id="session-1",
    )

    result = orchestrator.run(
        "Teach them the basics of managing money, for the Under 35 group.",
        [], scope=scope, session_id="session-1",
    )

    objective = registry.executed[0][1]["objective"]
    assert "Planning focus: general financial planning" in objective
    assert "Gender targeting: no gender restriction" in objective
    assert "Cash targeting: no cash restriction" in objective
    assert [call["schema_name"] for call in client.calls] == [
        "campaign_intent_extraction",
        "campaign_intent_extraction",
        "campaign_draft_generation",
    ]
    assert "Draft only — not created" in result


def test_pending_campaign_clarification_can_be_cancelled_without_model_call():
    store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        FakeClient([intent_extraction()]), settings(),
        CampaignGenerationRegistry(campaign_draft_artifact()),
        clarification_store=store,
    )
    scope = RequestScope("fa-1")
    orchestrator.run(
        "Create a campaign for students entering the workforce",
        [], scope=scope, session_id="session-1",
    )

    result = orchestrator.run(
        "cancel campaign draft", [], scope=scope, session_id="session-1"
    )

    assert store.status == "cancelled"
    assert "No campaign was created" in result


def test_unresolved_campaign_clarification_stops_after_three_answer_rounds():
    client = FakeClient([intent_extraction(audienceSpecified=False) for _ in range(4)])
    store = FakeClarificationStore()
    orchestrator = ChatOrchestrator(
        client, settings(), CampaignGenerationRegistry(campaign_draft_artifact()),
        clarification_store=store,
    )
    scope = RequestScope("fa-1")
    orchestrator.run(
        "Create a campaign", [], scope=scope, session_id="session-1"
    )

    for _ in range(2):
        response = orchestrator.run(
            "I am not sure yet", [], scope=scope, session_id="session-1"
        )
        assert "A few details" in response
    response = orchestrator.run(
        "I am still not sure", [], scope=scope, session_id="session-1"
    )

    assert store.status == "cancelled"
    assert "after three clarification rounds" in response
    assert "No campaign was generated or created" in response
    assert len(client.calls) == 4
    assert all(call["schema_name"] == "campaign_intent_extraction" for call in client.calls)


def test_campaign_draft_renderer_includes_every_structured_section():
    rendered = render_campaign_draft(
        CampaignDraftArtifact.model_validate(campaign_draft_artifact())
    )

    expected_sections = (
        "Campaign name", "Objective", "Description", "Client message",
        "Target criteria", "Target demographic", "Rationale", "Assumptions",
        "Disclaimer", "References used", "Validation",
    )
    for section in expected_sections:
        assert f"### {section}" in rendered
    assert "55–64" in rendered
    assert "All genders" in rendered
    assert "SGD 50,000–250,000" in rendered
    assert "The assumption requires adviser review." in rendered


def test_prepare_error_gets_a_deterministic_safe_explanation():
    artifact = {
        "data_source": "ai_generated",
        "error_code": "missing_disclaimer",
        "error": "The disclaimer is incomplete",
        "created": False,
    }
    generated = campaign_draft_artifact()
    client = FakeClient([
        completion(message(content=json.dumps({
            "referencesUsed": generated["referencesUsed"],
            "draft": generated["draft"],
        }))),
    ])
    orchestrator = ChatOrchestrator(
        client, settings(), CampaignGenerationRegistry(artifact)
    )

    result = orchestrator.run("Create a retirement campaign", [])

    assert "Campaign draft could not be prepared" in result
    assert "The disclaimer is incomplete" in result
    assert "No campaign was created" in result
    assert len(client.calls) == 1

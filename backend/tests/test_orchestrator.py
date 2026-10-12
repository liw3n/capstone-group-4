import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.campaigns.models import CampaignDraftArtifact
from app.campaigns.presentation import render_campaign_draft
from app.llm.errors import LLMProviderError, LLMToolLoopError
from app.llm.orchestrator import (
    ChatOrchestrator,
    SYSTEM_PROMPT,
    _is_campaign_generation_request,
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

    def create_structured_completion(self, messages, schema):
        self.calls.append({
            "messages": list(messages), "schema": schema, "structured": True,
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


@pytest.mark.parametrize(
    "message_value",
    [
        "I want to run a campaign encouraging clients nearing retirement",
        "Create a retirement campaign",
        "Generate a campaign draft for younger clients",
        "Campaign proposal for an educational retirement review",
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

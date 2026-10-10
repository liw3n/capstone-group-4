from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm.errors import LLMProviderError, LLMToolLoopError
from app.llm.orchestrator import ChatOrchestrator
from app.store import ChatHistoryItem


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
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.responses.pop(0)


def settings(**overrides):
    values = {
        "groq_api_key": "test-key",
        "llm_max_tool_rounds": 5,
        "llm_history_limit": 50,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_returns_plain_model_answer():
    client = FakeClient([completion(message(content="A real answer"))])
    orchestrator = ChatOrchestrator(client, settings())

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
    orchestrator = ChatOrchestrator(client, settings())

    result = orchestrator.run("What is two plus three?", [])

    assert result == "The total is 5."
    follow_up_messages = client.calls[1]["messages"]
    assert follow_up_messages[-1]["role"] == "tool"
    assert follow_up_messages[-1]["tool_call_id"] == "call-1"
    assert '"result": 5.0' in follow_up_messages[-1]["content"]


def test_preserves_user_and_assistant_history():
    client = FakeClient([completion(message(content="Next answer"))])
    orchestrator = ChatOrchestrator(client, settings())
    history = [
        ChatHistoryItem("2026-01-01T00:00:00Z", "fa-1", "Earlier question"),
        ChatHistoryItem("2026-01-01T00:00:01Z", False, "Earlier answer"),
    ]

    orchestrator.run("Next question", history)

    roles = [entry["role"] for entry in client.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_rejects_empty_provider_response():
    client = FakeClient([completion(message())])
    orchestrator = ChatOrchestrator(client, settings())

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
    )

    with pytest.raises(LLMToolLoopError, match="round limit"):
        orchestrator.run("Keep calculating", [])


def test_selected_campaign_context_overrides_history_without_mutating_registry():
    from app.campaigns.repository import DEMO_FA, RequestScope
    from app.tools import DEFAULT_TOOL_REGISTRY
    client = FakeClient([completion(message(content="Use camp-2"))])
    orchestrator = ChatOrchestrator(client, settings())
    history = [ChatHistoryItem("2026-08-25T00:00:00Z", False, "Earlier results for camp-1")]
    orchestrator.run("What about this campaign?", history,
                     scope=RequestScope(DEMO_FA), campaign_id="camp-2")
    assert '"campaign_id": "camp-2"' in client.calls[0]["messages"][0]["content"]
    assert client.calls[0]["messages"][1]["content"] == "Earlier results for camp-1"
    assert orchestrator.registry is DEFAULT_TOOL_REGISTRY

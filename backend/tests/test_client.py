import pytest
import httpx
from openai import BadRequestError

from app.llm import client as client_module
from app.config import Settings
from app.llm.client import LLMClient
from app.llm.errors import LLMConfigurationError


def _bad_request(error: dict) -> BadRequestError:
    request = httpx.Request("POST", "https://provider.example/chat/completions")
    response = httpx.Response(400, json={"error": error}, request=request)
    return BadRequestError("Bad request", response=response, body={"error": error})


def test_client_requires_api_key():
    settings = Settings(_env_file=None, groq_api_key=None)

    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY"):
        LLMClient(settings)


def test_client_uses_configured_openai_compatible_endpoint(monkeypatch):
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return "completion"

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(client_module, "OpenAI", FakeOpenAI)
    settings = Settings(
        _env_file=None,
        groq_api_key="test-key",
        llm_base_url="https://provider.example/openai/v1",
        llm_model="test-model",
    )

    client = LLMClient(settings)
    result = client.create_chat_completion(
        [{"role": "user", "content": "Hello"}],
        [{"type": "function", "function": {"name": "example"}}],
    )

    assert result == "completion"
    assert captured["client"]["api_key"] == "test-key"
    assert captured["client"]["base_url"] == "https://provider.example/openai/v1"
    assert captured["request"]["model"] == "test-model"
    assert captured["request"]["tool_choice"] == "auto"

    result = client.create_structured_completion(
        [{"role": "user", "content": "Generate a draft"}],
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    )

    assert result == "completion"
    assert "tools" not in captured["request"]
    response_format = captured["request"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["name"] == "campaign_draft_generation"
    assert response_format["json_schema"]["schema"]["required"] == ["name"]

    client.create_structured_completion(
        [{"role": "user", "content": "Extract intent"}],
        {"type": "object", "properties": {}, "required": []},
        schema_name="campaign_intent_extraction",
    )
    assert (
        captured["request"]["response_format"]["json_schema"]["name"]
        == "campaign_intent_extraction"
    )


def test_client_retries_malformed_tool_generation_once(monkeypatch):
    requests = []

    class Completions:
        def create(self, **kwargs):
            requests.append(kwargs)
            if len(requests) == 1:
                raise _bad_request({
                    "message": "Invalid tool call generated",
                    "failed_generation": {"reason": "Invalid tool arguments"},
                })
            return "completion"

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(client_module, "OpenAI", FakeOpenAI)
    client = LLMClient(Settings(_env_file=None, groq_api_key="test-key"))

    assert client.create_chat_completion(
        [{"role": "user", "content": "Synthetic question"}],
        [{"type": "function", "function": {"name": "example"}}],
    ) == "completion"
    assert len(requests) == 2
    assert requests[1]["temperature"] == 0.2


def test_client_does_not_retry_other_bad_requests(monkeypatch):
    requests = []

    class Completions:
        def create(self, **kwargs):
            requests.append(kwargs)
            raise _bad_request({"message": "Invalid request schema"})

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(client_module, "OpenAI", FakeOpenAI)
    client = LLMClient(Settings(_env_file=None, groq_api_key="test-key"))

    with pytest.raises(client_module.LLMProviderError, match="HTTP 400"):
        client.create_chat_completion(
            [{"role": "user", "content": "Synthetic question"}],
            [{"type": "function", "function": {"name": "example"}}],
        )
    assert len(requests) == 1

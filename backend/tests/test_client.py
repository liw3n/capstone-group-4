import pytest

from app.llm import client as client_module
from app.config import Settings
from app.llm.client import LLMClient
from app.llm.errors import LLMConfigurationError


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

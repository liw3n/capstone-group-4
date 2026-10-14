import pytest

from types import SimpleNamespace

from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("campaign_rows")

from app import main
from app.store import ChatHistoryItem, ChatSession, StoreUnavailableError


client = TestClient(main.app)


class FakeOrchestrator:
    def __init__(self, answer="Generated answer"):
        self.answer = answer
        self.calls = []

    def run(self, message, history, **context):
        self.calls.append((message, history, context))
        return self.answer


def session(fa_id="fa-1"):
    return ChatSession(
        session_id="session-1",
        fa_id=fa_id,
        timestamp="2026-10-03T00:00:00Z",
    )


def test_health_reports_llm_configuration_without_secret(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=True, llm_model="test-model"),
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "llm_configured": True,
        "llm_model": "test-model",
    }


def test_orchestrator_uses_configured_mcp_server(monkeypatch):
    from app.config import Settings
    from app.tools.mcp_registry import MCPToolRegistry

    settings = Settings(
        _env_file=None,
        groq_api_key="test-key",
        mcp_server_url="http://mcp.internal:8001/mcp",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "LLMClient", lambda _settings: object())
    main.get_orchestrator.cache_clear()
    try:
        orchestrator = main.get_orchestrator()
        assert isinstance(orchestrator.registry, MCPToolRegistry)
        assert orchestrator.registry.transport == "http://mcp.internal:8001/mcp"
    finally:
        main.get_orchestrator.cache_clear()


def test_query_calls_llm_and_persists_exchange(monkeypatch):
    orchestrator = FakeOrchestrator()
    persisted = []
    old_history = [
        ChatHistoryItem("2026-10-02T00:00:00Z", "fa-1", "Earlier question")
    ]
    monkeypatch.setattr(main, "latest_session", lambda _fa_id: session())
    monkeypatch.setattr(main, "get_history", lambda _session_id: old_history)
    monkeypatch.setattr(main, "get_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(
        main,
        "append_exchange",
        lambda *items: persisted.append(items),
    )

    response = client.post(
        "/chat/query",
        json={"fa_id": "fa-1", "message_content": "What is outstanding?"},
    )

    assert response.status_code == 200
    assert response.json()["ai_answer"] == "Generated answer"
    assert orchestrator.calls == [("What is outstanding?", old_history,
                                   {"scope": main.RequestScope("fa-1"),
                                    "campaign_id": None, "session_id": "session-1"})]
    assert persisted[0][0] == "session-1"
    assert persisted[0][1].message_content == "What is outstanding?"
    assert persisted[0][2].message_content == "Generated answer"


def test_api_alias_uses_same_query_handler(monkeypatch):
    monkeypatch.setattr(main, "latest_session", lambda _fa_id: session())
    monkeypatch.setattr(main, "get_history", lambda _session_id: [])
    monkeypatch.setattr(main, "get_orchestrator", lambda: FakeOrchestrator())
    monkeypatch.setattr(main, "append_exchange", lambda *_items: None)

    response = client.post(
        "/api/chat/query",
        json={"fa_id": "fa-1", "message_content": "Hello"},
    )

    assert response.status_code == 200


def test_query_rejects_session_owned_by_another_adviser(monkeypatch):
    monkeypatch.setattr(main, "get_session", lambda _session_id: session("fa-2"))

    response = client.post(
        "/chat/query",
        json={
            "fa_id": "fa-1",
            "session_id": "session-1",
            "message_content": "Hello",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "chat session not found"}


def test_query_rejects_whitespace_only_message():
    response = client.post(
        "/chat/query",
        json={"fa_id": "fa-1", "message_content": "   "},
    )

    assert response.status_code == 422


def test_storage_failure_is_mapped_to_service_unavailable(monkeypatch):
    def fail(_fa_id):
        raise StoreUnavailableError("chat storage is temporarily unavailable")

    monkeypatch.setattr(main, "list_sessions", fail)

    response = client.get("/chat/sessions", params={"fa_id": "fa-1"})

    assert response.status_code == 503
    assert response.json() == {"detail": "chat storage is temporarily unavailable"}


def test_selected_campaign_is_forwarded_on_both_routes(monkeypatch):
    from app.campaigns.repository import DEMO_FA, RequestScope
    orchestrator = FakeOrchestrator()
    monkeypatch.setattr(main, "latest_session", lambda _fa_id: session(DEMO_FA))
    monkeypatch.setattr(main, "get_history", lambda _session_id: [])
    monkeypatch.setattr(main, "get_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(main, "append_exchange", lambda *_items: None)
    for route in ("/chat/query", "/api/chat/query"):
        response = client.post(route, json={"fa_id": DEMO_FA, "campaign_id": "camp-1",
                                           "message_content": "Who matches this campaign?"})
        assert response.status_code == 200
        assert orchestrator.calls[-1][2] == {
            "scope": RequestScope(DEMO_FA),
            "campaign_id": "camp-1",
            "session_id": "session-1",
        }


def test_selected_invalid_or_inaccessible_campaign_fails_before_storage(monkeypatch):
    def should_not_read(_fa_id):
        raise AssertionError("Campaign validation should happen before storage")
    monkeypatch.setattr(main, "latest_session", should_not_read)
    cases = [("camp-1", "adv-other-demo", 404), ("camp-missing", "adv-steven-raynaldi", 404),
             ("bad id", "adv-steven-raynaldi", 422),
             ("6efc8b88-6f67-4654-9d03-84e0cb741190", "adv-steven-raynaldi", 404)]
    for campaign_id, fa_id, expected in cases:
        response = client.post("/api/chat/query", json={
            "fa_id": fa_id, "campaign_id": campaign_id, "message_content": "Who matches?"
        })
        assert response.status_code == expected


def test_inactive_selected_campaign_returns_conflict(monkeypatch):
    from dataclasses import replace
    from campaign_fixtures import CAMPAIGNS
    from app.campaigns.repository import DEMO_FA
    monkeypatch.setattr(main, "get_campaign", lambda *_args: replace(CAMPAIGNS[0], status="completed"))
    response = client.post("/chat/query", json={
        "fa_id": DEMO_FA, "campaign_id": "camp-1", "message_content": "Who matches?"
    })
    assert response.status_code == 409


def test_whitespace_adviser_is_rejected():
    response = client.post("/chat/query", json={"fa_id": "  ", "message_content": "Hello"})
    assert response.status_code == 400


def test_query_runs_real_mcp_recommendation_with_fake_provider_and_storage(monkeypatch):
    import json
    from app.campaigns.repository import DEMO_FA
    from app.llm.orchestrator import ChatOrchestrator
    from app.tools.mcp_registry import MCPToolRegistry
    from test_campaign_mcp import server
    from test_orchestrator import FakeClient, completion, message, settings, tool_call

    provider = FakeClient([
        completion(message(tool_calls=[tool_call(
            "recommend-1", "recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'
        )])),
        completion(message(content="Synthetic criteria matches: A, B, C and L. Not financial advice.")),
    ])
    orchestrator = ChatOrchestrator(provider, settings(), MCPToolRegistry(server))
    monkeypatch.setattr(main, "latest_session", lambda _fa_id: session(DEMO_FA))
    monkeypatch.setattr(main, "get_history", lambda _session_id: [])
    monkeypatch.setattr(main, "get_orchestrator", lambda: orchestrator)
    persisted = []
    monkeypatch.setattr(main, "append_exchange", lambda *items: persisted.append(items))
    response = client.post("/api/chat/query", json={
        "fa_id": DEMO_FA, "campaign_id": "camp-1",
        "message_content": "Which clients are recommended for this campaign?"
    })
    assert response.status_code == 200
    tool_result = json.loads(provider.calls[1]["messages"][-1]["content"])
    assert tool_result["matched_count"] == 4
    assert tool_result["evaluated_count"] == 12
    assert '"campaign_id": "camp-1"' in provider.calls[0]["messages"][0]["content"]
    assert len(persisted) == 1

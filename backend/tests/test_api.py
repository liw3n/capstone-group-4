from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.store import ChatHistoryItem, ChatSession, StoreUnavailableError


client = TestClient(main.app)


class FakeOrchestrator:
    def __init__(self, answer="Generated answer"):
        self.answer = answer
        self.calls = []

    def run(self, message, history):
        self.calls.append((message, history))
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
    assert orchestrator.calls == [("What is outstanding?", old_history)]
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

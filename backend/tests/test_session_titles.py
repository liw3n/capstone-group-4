from app import store
from app.store import ChatHistoryItem


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters=()):
        self.calls.append((" ".join(query.split()), parameters))


def test_first_exchange_sets_session_title_from_first_five_words(monkeypatch):
    connection = RecordingConnection()
    monkeypatch.setattr(store, "_connection", lambda: connection)

    store.append_exchange(
        "session-1",
        ChatHistoryItem("2026-10-11T00:00:00Z", "fa-1",
                        "Please review my campaign follow-up list"),
        ChatHistoryItem("2026-10-11T00:00:01Z", False, "Here is the list."),
    )

    title_update = next(
        call for call in connection.calls if call[0].startswith("UPDATE campaign_chat_sessions")
    )
    assert title_update == (
        "UPDATE campaign_chat_sessions SET session_title = %s "
        "WHERE session_id = %s AND (session_title IS NULL OR session_title = 'New chat')",
        ("Please review my campaign follow-up...", "session-1"),
    )

from datetime import datetime, timezone

from app import store


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.startswith("INSERT INTO campaign_chat_sessions"):
            session_id, fa_id, session_title = params
            row = {
                "session_id": session_id,
                "fa_id": fa_id,
                "timestamp": datetime.now(timezone.utc),
                "session_title": session_title,
            }
            self.database["sessions"].append(row)
            return FakeResult([row])

        if "FROM campaign_chat_sessions" in normalized and "WHERE fa_id" in normalized:
            rows = [
                row for row in self.database["sessions"] if row["fa_id"] == params[0]
            ]
            return FakeResult(rows)

        raise AssertionError(f"Unexpected SQL: {normalized}")


def test_created_session_is_visible_to_a_new_database_connection(monkeypatch):
    database = {"sessions": []}
    connections = []

    def connect(*_args, **_kwargs):
        connection = FakeConnection(database)
        connections.append(connection)
        return connection

    monkeypatch.setattr(store, "_database_url", lambda: "postgresql://test")
    monkeypatch.setattr(store.psycopg, "connect", connect)

    created = store.create_session("fa-1")
    listed = store.list_sessions("fa-1")

    assert len(connections) == 2
    assert [item.session_id for item in listed] == [created.session_id]

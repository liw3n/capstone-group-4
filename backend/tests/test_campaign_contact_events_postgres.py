"""Opt-in PostgreSQL checks for synthetic, adviser-scoped contact history."""
from datetime import datetime
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config

TABLES = Path(__file__).parents[1] / "tables"
CONTACT_EVENT_TABLE_SQL = TABLES / "create_mock_campaign_contact_event.sql"
CONTACT_EVENT_SEED_SQL = TABLES / "seed_mock_campaign_contact_events.sql"


@pytest.fixture
def database(monkeypatch):
    database_url = os.environ.get("PULSE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set PULSE_TEST_DATABASE_URL to a local disposable PostgreSQL database")
    schema = "pulse_contacts_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        scoped_url = make_conninfo(database_url, options="-c search_path=" + schema)
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                for name in ("create_mock_campaign_tables.sql", "seed_mock_campaign_data.sql"):
                    connection.execute((TABLES / name).read_text())
                monkeypatch.setattr(config, "get_settings",
                                    lambda: SimpleNamespace(database_url=scoped_url))
                yield connection
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_contacts_link_to_existing_campaign_names_and_keep_first_date(database):
    database.execute(CONTACT_EVENT_TABLE_SQL.read_text())
    database.execute(CONTACT_EVENT_SEED_SQL.read_text())
    database.execute(CONTACT_EVENT_TABLE_SQL.read_text())
    database.execute(CONTACT_EVENT_SEED_SQL.read_text())
    assert database.execute("SELECT count(*) FROM mock_campaign_contact_event").fetchone()[0] == 12

    rows = database.execute("""
        SELECT c.name, e.contact_id, min(e.contacted_at), count(*)
        FROM mock_campaign_contact_event AS e
        JOIN mock_campaign AS c
          ON c.tenant_id = e.tenant_id AND c.campaign_id = e.campaign_id
        WHERE e.tenant_id = 'pulse-demo' AND e.fa_id = 'adv-steven-raynaldi'
        GROUP BY c.name, e.contact_id
    """).fetchall()
    assert len(rows) == 10  # Repeated contacts count as one client per campaign.
    by_campaign_client = {(name, client_id): (first, count)
                          for name, client_id, first, count in rows}
    first, count = by_campaign_client[("Legacy Protection Refresh", "client-005")]
    assert first == datetime.fromisoformat("2026-08-05T13:00:00+08:00")
    assert count == 2
    assert ("First Home Starter Bundle", "client-009") in by_campaign_client


def test_contact_cannot_use_another_advisors_client_or_campaign(database):
    database.execute(CONTACT_EVENT_TABLE_SQL.read_text())
    database.execute(CONTACT_EVENT_SEED_SQL.read_text())
    # Client 013 belongs to another FA, who is not assigned to these campaigns.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        database.execute("""
            INSERT INTO mock_campaign_contact_event
                (tenant_id, contact_event_id, campaign_id, fa_id, contact_id, contacted_at)
            VALUES ('pulse-demo', 'invalid-client', 'camp-1',
                    'adv-steven-raynaldi', 'client-013', '2026-10-12 14:00:00+08')
        """)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        database.execute("""
            INSERT INTO mock_campaign_contact_event
                (tenant_id, contact_event_id, campaign_id, fa_id, contact_id, contacted_at)
            VALUES ('pulse-demo', 'invalid-advisor', 'camp-1',
                    'adv-other-demo', 'client-013', '2026-10-12 14:00:00+08')
        """)


def test_real_mcp_counts_contacts_within_period_and_adviser_scope(database, monkeypatch):
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.tools import performance
    from app.tools.mcp_registry import MCPToolRegistry
    from app.campaigns.repository import RequestScope
    from test_campaign_mcp import server

    database.execute(CONTACT_EVENT_TABLE_SQL.read_text())
    database.execute(CONTACT_EVENT_SEED_SQL.read_text())
    monkeypatch.setattr(performance, "current_time",
                        lambda: datetime(2026, 10, 12, 18, 0,
                                         tzinfo=ZoneInfo("Asia/Singapore")))
    # Events outside the campaign and an additional repeat must not inflate totals.
    database.execute("""
        INSERT INTO mock_campaign_contact_event
            (tenant_id, contact_event_id, campaign_id, fa_id, contact_id, contacted_at)
        VALUES
            ('pulse-demo', 'outside-end', 'camp-1', 'adv-steven-raynaldi',
             'client-010', '2027-01-01 09:00:00+08'),
            ('pulse-demo', 'future-today', 'camp-1', 'adv-steven-raynaldi',
             'client-011', '2026-10-12 20:00:00+08')
    """)
    registry = MCPToolRegistry(server).bind_scope(RequestScope("adv-steven-raynaldi"))
    camp1 = json.loads(registry.execute("get_campaign_contact_performance",
                                        '{"campaign":"Legacy Protection Refresh"}'))
    assert (camp1["contacted_clients_total"], camp1["contacted_clients_this_week"],
            camp1["first_contacted_clients_this_week"]) == (6, 1, 1)
    camp2 = json.loads(registry.execute("get_campaign_contact_performance",
                                        '{"campaign":"camp-2"}'))
    assert (camp2["contacted_clients_total"], camp2["contacted_clients_this_week"],
            camp2["first_contacted_clients_this_week"]) == (4, 2, 2)
    last_week = json.loads(registry.execute("get_campaign_contact_performance",
        '{"campaign":"camp-2","period":"last_week"}'))
    assert last_week["requested_period"] == "last_week"
    assert (last_week["contacted_clients_last_week"],
            last_week["first_contacted_clients_last_week"]) == (2, 2)
    assert last_week["last_week_start_date"] == "2026-10-05"
    assert last_week["last_week_end_date"] == "2026-10-11"
    assert "2 clients were contacted last week" in last_week["summary"]
    assert camp1["contacted_clients_last_week"] == 0
    other = MCPToolRegistry(server).bind_scope(RequestScope("adv-other-demo"))
    denied = json.loads(other.execute("get_campaign_contact_performance",
                                      '{"campaign":"camp-1"}'))
    assert denied["error_code"] == "campaign_unavailable"
    assert "contacted_clients_total" not in denied


def test_chat_routes_pass_contact_performance_tool_result(database, monkeypatch):
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from app import main, store
    from app.llm.orchestrator import ChatOrchestrator
    from app.tools import performance
    from app.tools.mcp_registry import MCPToolRegistry
    from test_campaign_mcp import server
    from test_orchestrator import FakeClient, completion, message, settings, tool_call

    database.execute(CONTACT_EVENT_TABLE_SQL.read_text())
    database.execute(CONTACT_EVENT_SEED_SQL.read_text())
    database.execute((TABLES / "create_campaign_chat_sessions.sql").read_text())
    monkeypatch.setattr(store, "get_settings", config.get_settings)
    monkeypatch.setattr(performance, "current_time",
                        lambda: datetime(2026, 10, 12, 18, 0,
                                         tzinfo=ZoneInfo("Asia/Singapore")))

    client = TestClient(main.app)
    for route in ("/chat/query", "/api/chat/query"):
        provider = FakeClient([
            completion(message(tool_calls=[tool_call(
                "performance-pg", "get_campaign_contact_performance", "{}"
            )])),
            completion(message(content=("Legacy Protection Refresh is ongoing. "
                "As of 12 October 2026, 6 clients have been contacted. "
                "1 was contacted this week. (Synthetic data.)"))),
        ])
        orchestrator = ChatOrchestrator(provider, settings(), MCPToolRegistry(server))
        monkeypatch.setattr(main, "get_orchestrator", lambda: orchestrator)
        response = client.post(route, json={
            "fa_id": "adv-steven-raynaldi", "campaign_id": "camp-1",
            "message_content": "How many clients have been contacted this week?",
        })
        assert response.status_code == 200
        assert "6 clients" in response.json()["ai_answer"]
        tool_result = json.loads(provider.calls[1]["messages"][-1]["content"])
        assert tool_result["contacted_clients_total"] == 6
        assert tool_result["contacted_clients_this_week"] == 1


def test_chat_route_passes_last_week_selection_to_tool(database, monkeypatch):
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from app import main, store
    from app.llm.orchestrator import ChatOrchestrator
    from app.tools import performance
    from app.tools.mcp_registry import MCPToolRegistry
    from test_campaign_mcp import server
    from test_orchestrator import FakeClient, completion, message, settings, tool_call

    database.execute(CONTACT_EVENT_TABLE_SQL.read_text())
    database.execute(CONTACT_EVENT_SEED_SQL.read_text())
    database.execute((TABLES / "create_campaign_chat_sessions.sql").read_text())
    monkeypatch.setattr(store, "get_settings", config.get_settings)
    monkeypatch.setattr(performance, "current_time",
                        lambda: datetime(2026, 10, 12, 18, 0,
                                         tzinfo=ZoneInfo("Asia/Singapore")))

    provider = FakeClient([
        completion(message(tool_calls=[tool_call(
            "performance-last-week", "get_campaign_contact_performance",
            '{"period":"last_week"}'
        )])),
        completion(message(content="2 clients were contacted last week (synthetic data).")),
    ])
    orchestrator = ChatOrchestrator(provider, settings(), MCPToolRegistry(server))
    monkeypatch.setattr(main, "get_orchestrator", lambda: orchestrator)
    response = TestClient(main.app).post("/chat/query", json={
        "fa_id": "adv-steven-raynaldi", "campaign_id": "camp-2",
        "message_content": "How many did I contact for this campaign last week?",
    })
    assert response.status_code == 200
    assert "2 clients" in response.json()["ai_answer"]
    tool_result = json.loads(provider.calls[1]["messages"][-1]["content"])
    assert tool_result["requested_period"] == "last_week"
    assert tool_result["contacted_clients_last_week"] == 2

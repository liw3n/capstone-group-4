"""Opt-in integration tests against PostgreSQL in an isolated temporary schema."""
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config
from app.campaigns import repository
from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import CampaignInactive, CampaignUnavailable, DEMO_FA, RequestScope

TABLES = Path(__file__).parents[1] / "tables"


@pytest.fixture
def database(monkeypatch):
    database_url = os.environ.get("PULSE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set PULSE_TEST_DATABASE_URL to a local disposable PostgreSQL database")
    schema = "pulse_campaign_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        scoped_url = make_conninfo(database_url, options="-c search_path=" + schema)
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                connection.execute((TABLES / "create_mock_campaign_tables.sql").read_text())
                connection.execute((TABLES / "seed_mock_campaign_data.sql").read_text())
                monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=scoped_url))
                yield connection
        finally:
            # Delete only the uniquely named schema created by this test.
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_seed_is_repeatable_and_matches_are_read_from_postgres(database):
    database.execute((TABLES / "create_mock_campaign_tables.sql").read_text())
    database.execute((TABLES / "seed_mock_campaign_data.sql").read_text())
    assert database.execute("SELECT count(*) FROM mock_campaign").fetchone()[0] == 2
    assert database.execute("SELECT count(*) FROM mock_client").fetchone()[0] == 14
    assert database.execute("SELECT count(*) FROM mock_campaign_advisor").fetchone()[0] == 2
    assert database.execute("SELECT count(*) FROM mock_client WHERE opt_in_email OR opt_in_sms").fetchone()[0] == 0
    for campaign_id, ids, excluded in (
        ("camp-1", ["client-001", "client-002", "client-003", "client-012"], 6),
        ("camp-2", ["client-006", "client-007", "client-008"], 7),
    ):
        result = recommend_clients_for_campaign(campaign_id, RequestScope(DEMO_FA))
        assert [c["contact_id"] for c in result["clients"]] == ids
        assert result["evaluated_count"] == 12
        assert result["incomplete_count"] == 2
        assert result["excluded_count"] == excluded


def test_database_filters_adviser_and_tenant_even_for_duplicate_campaign_ids(database):
    scope = RequestScope(DEMO_FA)
    assert len(repository.list_clients_for_fa(scope)) == 12
    assert len(repository.list_clients_for_fa(RequestScope("adv-other-demo"))) == 1
    assert len(repository.list_clients_for_fa(RequestScope(DEMO_FA, "other-demo-tenant"))) == 1
    for other_scope in (RequestScope("adv-other-demo"), RequestScope(DEMO_FA, "other-demo-tenant")):
        with pytest.raises(CampaignUnavailable):
            repository.get_campaign("camp-1", other_scope)
    database.execute(
        """INSERT INTO mock_campaign (tenant_id, campaign_id, name, status, start_date, end_date)
           VALUES (%s, 'camp-1', 'Other tenant synthetic campaign', 'active', '2026-08-01', '2026-12-31')""",
        ("other-demo-tenant",),
    )
    database.execute("INSERT INTO mock_campaign_advisor VALUES (%s, 'camp-1', %s)",
                     ("other-demo-tenant", DEMO_FA))
    assert repository.get_campaign("camp-1", scope).name == "Legacy Protection Refresh"
    result = recommend_clients_for_campaign("camp-1", RequestScope(DEMO_FA, "other-demo-tenant"))
    assert result["evaluated_count"] == 1
    assert result["clients"][0]["contact_id"] == "client-014"
    # An assignment cannot point across tenant boundaries.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        database.execute("INSERT INTO mock_campaign_advisor VALUES ('missing-tenant', 'camp-1', %s)", (DEMO_FA,))


def test_new_connections_observe_committed_changes_and_reseeding_preserves_edits(database):
    scope = RequestScope(DEMO_FA)
    before = recommend_clients_for_campaign("camp-1", scope)
    database.execute("UPDATE mock_client SET available_cash = 0 WHERE tenant_id = 'pulse-demo' AND contact_id = 'client-001'")
    after = recommend_clients_for_campaign("camp-1", scope)
    assert after["matched_count"] == before["matched_count"] - 1
    database.execute((TABLES / "seed_mock_campaign_data.sql").read_text())
    assert recommend_clients_for_campaign("camp-1", scope)["matched_count"] == after["matched_count"]


def test_numeric_ranges_dates_and_nullable_profiles_round_trip(database):
    database.execute("""UPDATE mock_campaign SET age_groups = '{}', cash_bands = '{}',
        genders = ARRAY['female'], age_min = 58, age_max = 58, cash_min = 300000, cash_max = 300000
        WHERE tenant_id = 'pulse-demo' AND campaign_id = 'camp-1'""")
    result = recommend_clients_for_campaign("camp-1", RequestScope(DEMO_FA))
    assert [c["contact_id"] for c in result["clients"]] == ["client-001"]
    assert result["incomplete_count"] == 3
    client = repository.list_clients_for_fa(RequestScope(DEMO_FA))[0]
    assert client.dob == "1968-08-26"
    assert client.available_cash == 300000


def test_inactive_and_invalid_ids_do_not_read_clients(database, monkeypatch):
    def forbidden_read(_scope):
        raise AssertionError("Must validate campaign before reading clients")
    monkeypatch.setattr(repository, "_load_clients", forbidden_read)
    for status in ("draft", "paused", "completed"):
        database.execute("UPDATE mock_campaign SET status = %s WHERE campaign_id = 'camp-1'", (status,))
        with pytest.raises(CampaignInactive):
            recommend_clients_for_campaign("camp-1", RequestScope(DEMO_FA))
    database.execute("UPDATE mock_campaign SET status = 'active', end_date = '2026-08-25' WHERE campaign_id = 'camp-1'")
    with pytest.raises(CampaignInactive):
        recommend_clients_for_campaign("camp-1", RequestScope(DEMO_FA))
    for campaign_id in ("camp-missing", "bad id", "camp-1' OR '1'='1"):
        with pytest.raises(CampaignUnavailable):
            recommend_clients_for_campaign(campaign_id, RequestScope(DEMO_FA))


@pytest.mark.parametrize("statement", [
    "UPDATE mock_campaign SET age_groups = ARRAY['invalid']",
    "UPDATE mock_campaign SET age_groups = ARRAY[NULL]::text[]",
    "UPDATE mock_campaign SET cash_min = 100, cash_max = 99",
    "UPDATE mock_campaign SET end_date = '2020-01-01'",
    "UPDATE mock_client SET available_cash = -1",
    "UPDATE mock_client SET available_cash = 'NaN'::numeric",
    "UPDATE mock_client SET gender = 'invalid'",
])
def test_schema_rejects_unsupported_criteria_and_invalid_values(database, statement):
    with pytest.raises(psycopg.errors.CheckViolation):
        database.execute(statement)


def test_postgres_to_real_mcp_tool(database):
    import json
    from app.tools.mcp_registry import MCPToolRegistry
    from test_campaign_mcp import server
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute("recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'))
    assert result["data_source"] == "synthetic"
    assert result["matched_count"] == 4
    assert result["evaluated_count"] == 12


def test_api_to_mcp_recommendation_persists_chat_in_postgres(database, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from app import main, store
    from app.llm.orchestrator import ChatOrchestrator
    from app.tools.mcp_registry import MCPToolRegistry
    from test_campaign_mcp import server
    from test_orchestrator import FakeClient, completion, message, settings, tool_call

    database.execute((TABLES / "create_campaign_chat_sessions.sql").read_text())
    monkeypatch.setattr(store, "get_settings", config.get_settings)
    provider = FakeClient([
        completion(message(tool_calls=[tool_call(
            "recommend-pg", "recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'
        )])),
        completion(message(content="Synthetic criteria matches: A, B, C and L. Not financial advice.")),
    ])
    orchestrator = ChatOrchestrator(provider, settings(), MCPToolRegistry(server))
    monkeypatch.setattr(main, "get_orchestrator", lambda: orchestrator)
    client = TestClient(main.app)
    for route in ("/chat/query", "/api/chat/query"):
        response = client.post(route, json={"fa_id": DEMO_FA, "campaign_id": "camp-1",
            "message_content": "Which clients match this campaign?"})
        assert response.status_code == 200
        # Supply the next pair of deterministic provider responses for the alias request.
        if route == "/chat/query":
            tool_result = json.loads(provider.calls[1]["messages"][-1]["content"])
            assert tool_result["matched_count"] == 4
            provider.responses.extend([
                completion(message(tool_calls=[tool_call(
                    "recommend-pg-alias", "recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'
                )])),
                completion(message(content="Synthetic criteria matches: A, B, C and L. Not financial advice.")),
            ])
    assert database.execute("SELECT count(*) FROM campaign_chat_sessions").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM campaign_chat_messages").fetchone()[0] == 4
    assert len(store.get_history(store.latest_session(DEMO_FA).session_id)) == 4

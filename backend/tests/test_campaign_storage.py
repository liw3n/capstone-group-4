from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.campaigns.repository import CampaignStorageUnavailable, DEMO_FA, RequestScope, get_campaign
from app.tools.campaign import execute_recommendation


def test_missing_configuration_is_explicit_and_has_no_fixture_fallback(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=None))
    with pytest.raises(CampaignStorageUnavailable, match="not configured"):
        get_campaign("camp-1", RequestScope(DEMO_FA))


def test_connection_errors_do_not_expose_credentials(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url="test-connection"))
    def fail(*_args, **_kwargs):
        raise psycopg.OperationalError("raw confidential connection details")
    monkeypatch.setattr(psycopg, "connect", fail)
    with pytest.raises(CampaignStorageUnavailable) as error:
        get_campaign("camp-1", RequestScope(DEMO_FA))
    assert str(error.value) == "Campaign database is temporarily unavailable"
    result = execute_recommendation("camp-1", 100,
        {"pulse_scope": {"fa_id": DEMO_FA, "tenant_id": "pulse-demo"}})
    assert result["error_code"] == "storage_unavailable"
    assert "confidential" not in str(result)
    assert "clients" not in result


def test_both_api_routes_map_campaign_storage_failure_to_503(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=None))
    def forbidden(*_args):
        raise AssertionError("Must not call provider or chat storage on campaign database failure")
    monkeypatch.setattr(main, "latest_session", forbidden)
    monkeypatch.setattr(main, "get_orchestrator", forbidden)
    client = TestClient(main.app)
    for route in ("/chat/query", "/api/chat/query"):
        response = client.post(route, json={"fa_id": DEMO_FA,
            "campaign_id": "camp-1", "message_content": "Who matches?"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Campaign database is not configured"}

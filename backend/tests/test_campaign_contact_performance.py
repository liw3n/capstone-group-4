"""Read-only campaign contact performance through the real MCP tool."""
import asyncio
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

from fastmcp import Client
import pytest

from app.campaigns import repository
from app.campaigns.repository import DEMO_FA, RequestScope
from app.tools import performance
from app.tools.mcp_registry import MCPToolRegistry
from test_campaign_mcp import server

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=ZoneInfo("Asia/Singapore"))


@pytest.fixture(autouse=True)
def campaign_data(campaign_rows, monkeypatch):
    monkeypatch.setattr(performance, "current_time", lambda: NOW)


def call(args=None, scope=None, selected_id=None):
    registry = MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA), selected_id)
    return json.loads(registry.execute("get_campaign_contact_performance", json.dumps(args or {})))


def test_model_schema_exposes_campaign_but_no_adviser_identity():
    schemas = MCPToolRegistry(server).schemas()
    schema = next(item["function"]["parameters"] for item in schemas
                  if item["function"]["name"] == "get_campaign_contact_performance")
    assert set(schema["properties"]) == {"campaign"}


def test_selected_campaign_returns_grounded_distinct_counts(monkeypatch):
    def counts(scope, campaign_id, start, end, week_start):
        assert scope.fa_id == DEMO_FA and scope.tenant_id == "pulse-demo"
        assert campaign_id == "camp-1"
        assert start.isoformat() == "2026-08-01T00:00:00+08:00"
        assert end == NOW
        assert week_start.isoformat() == "2026-10-12T00:00:00+08:00"
        return 12, 5, 3
    monkeypatch.setattr(repository, "count_campaign_contacts", counts)
    result = call({"campaign": "First Home Starter Bundle"}, selected_id="camp-1")
    assert result["campaign_id"] == "camp-1"  # Server selection takes precedence.
    assert result["reporting_state"] == "ongoing"
    assert result["contacted_clients_total"] == 12
    assert result["contacted_clients_this_week"] == 5
    assert result["first_contacted_clients_this_week"] == 3
    assert result["summary"] == ("Legacy Protection Refresh is ongoing. "
                                 "As of 12 October 2026, 12 clients have been contacted. "
                                 "5 were contacted this week.")
    assert result["data_source"] == "synthetic"


def test_exact_name_resolution_and_missing_campaign(monkeypatch):
    from campaign_fixtures import CAMPAIGNS
    monkeypatch.setattr(repository, "get_campaign_by_name", lambda name, scope: CAMPAIGNS[1]
                        if name.lower() == CAMPAIGNS[1].name.lower() and scope.fa_id == DEMO_FA
                        else (_ for _ in ()).throw(repository.CampaignUnavailable("Unavailable")))
    monkeypatch.setattr(repository, "count_campaign_contacts", lambda *_: (4, 2, 2))
    assert call({"campaign": "first home starter bundle"})["campaign_id"] == "camp-2"
    assert call()["error_code"] == "missing_campaign"


def test_scope_and_argument_failures_do_not_read_counts(monkeypatch):
    monkeypatch.setattr(repository, "count_campaign_contacts",
                        lambda *_: (_ for _ in ()).throw(AssertionError("count must not run")))
    monkeypatch.setattr(repository, "get_campaign_by_name", lambda *_: (_ for _ in ()).throw(
        repository.CampaignUnavailable("Campaign not found or unavailable to this adviser")))
    assert call(selected_id="camp-1", scope=RequestScope("adv-other-demo"))["error_code"] == "campaign_unavailable"
    assert call({"campaign": "bad campaign"})["error_code"] == "campaign_unavailable"
    for args in ({"fa_id": DEMO_FA}, {"tenant_id": "pulse-demo"},
                 {"campaign": "camp-1", "ctx": {}}):
        assert call(args)["error"] == "Invalid tool arguments"
    assert call({"campaign": " "})["error_code"] == "missing_campaign"
    async def unscoped():
        async with Client(server) as client:
            return await client.call_tool("get_campaign_contact_performance",
                                          {"campaign": "camp-1"})
    assert asyncio.run(unscoped()).data["error_code"] == "missing_context"


def test_storage_failure_and_completed_period(monkeypatch):
    def fail(*_):
        raise repository.CampaignStorageUnavailable("Campaign database is temporarily unavailable")
    monkeypatch.setattr(repository, "count_campaign_contacts", fail)
    result = call(selected_id="camp-1")
    assert result["error_code"] == "storage_unavailable"
    assert "contacted_clients_total" not in result

    from dataclasses import replace
    from campaign_fixtures import CAMPAIGNS
    monkeypatch.setattr(repository, "get_campaign", lambda *_: replace(
        CAMPAIGNS[0], status="completed", end_date=NOW.date() - timedelta(days=1)))
    monkeypatch.setattr(repository, "count_campaign_contacts", lambda scope, campaign_id,
                        start, end, week_start: (6, 0, 0))
    completed = call(selected_id="camp-1")
    assert completed["reporting_state"] == "completed"
    assert completed["summary"].startswith("Legacy Protection Refresh has ended.")

"""Read-only campaign contact ranking through the real MCP tool."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.campaigns import repository
from app.campaigns.repository import DEMO_FA, RequestScope
from app.tools import performance
from app.tools.mcp_registry import MCPToolRegistry
from test_campaign_mcp import server

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=ZoneInfo("Asia/Singapore"))


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(performance, "current_time", lambda: NOW)


def call(args=None, scope=None, selected_id=None):
    registry = MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA), selected_id)
    return json.loads(registry.execute("get_campaign_contact_ranking", json.dumps(args or {})))


def row(campaign_id, name, count, campaign_count=2, tie_count=1):
    return {"campaign_id": campaign_id, "name": name, "status": "active",
            "contacted_clients": count, "campaign_count": campaign_count,
            "tie_count": tie_count}


def test_schema_exposes_period_without_adviser_or_campaign():
    schemas = MCPToolRegistry(server).schemas()
    schema = next(item["function"]["parameters"] for item in schemas
                  if item["function"]["name"] == "get_campaign_contact_ranking")
    assert set(schema["properties"]) == {"period"}


def test_default_ranks_all_accessible_campaigns_even_when_one_is_selected(monkeypatch):
    def rank(scope, start, end):
        assert scope.fa_id == DEMO_FA and scope.tenant_id == "pulse-demo"
        assert start is None and end == NOW
        return (row("camp-1", "Legacy Protection Refresh", 8),
                row("camp-2", "First Home Starter Bundle", 5))
    monkeypatch.setattr(repository, "rank_campaigns_by_contacts", rank)
    result = call(selected_id="camp-2")
    assert result["requested_period"] == "campaign_to_date"
    assert result["campaign_count"] == 2
    assert result["highest_contacted_clients"] == 8
    assert [item["campaign_id"] for item in result["leaders"]] == ["camp-1"]
    assert [item["contacted_clients"] for item in result["ranked_campaigns"]] == [8, 5]
    assert "Legacy Protection Refresh" in result["summary"]
    assert result["data_source"] == "synthetic"


def test_last_week_bounds_and_ties(monkeypatch):
    def rank(scope, start, end):
        assert start.isoformat() == "2026-10-05T00:00:00+08:00"
        assert end.isoformat() == "2026-10-12T00:00:00+08:00"
        return (row("camp-1", "Legacy Protection Refresh", 3, tie_count=2),
                row("camp-2", "First Home Starter Bundle", 3, tie_count=2))
    monkeypatch.setattr(repository, "rank_campaigns_by_contacts", rank)
    result = call({"period": "last_week"})
    assert result["period_start_date"] == "2026-10-05"
    assert result["period_end_date"] == "2026-10-11"
    assert len(result["leaders"]) == 2
    assert "tied" in result["summary"]


def test_zero_counts_empty_scope_and_validation(monkeypatch):
    monkeypatch.setattr(repository, "rank_campaigns_by_contacts",
                        lambda *_: (row("camp-1", "Legacy Protection Refresh", 0),
                                    row("camp-2", "First Home Starter Bundle", 0)))
    assert "No recorded clients" in call()["summary"]
    monkeypatch.setattr(repository, "rank_campaigns_by_contacts", lambda *_: ())
    assert call()["campaign_count"] == 0
    assert call()["leaders"] == []
    for args in ({"fa_id": DEMO_FA}, {"campaign": "camp-1"},
                 {"period": "yesterday"}):
        assert call(args)["error"] == "Invalid tool arguments"


def test_unavailable_storage_has_no_counts(monkeypatch):
    def fail(*_):
        raise repository.CampaignStorageUnavailable("Campaign database is temporarily unavailable")
    monkeypatch.setattr(repository, "rank_campaigns_by_contacts", fail)
    result = call()
    assert result["error_code"] == "storage_unavailable"
    assert "ranked_campaigns" not in result


def test_missing_scope_is_rejected():
    from fastmcp import Client
    import asyncio

    async def unscoped():
        async with Client(server) as client:
            return await client.call_tool("get_campaign_contact_ranking", {})
    assert asyncio.run(unscoped()).data["error_code"] == "missing_context"

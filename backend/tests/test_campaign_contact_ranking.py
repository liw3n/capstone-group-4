"""Campaign ranking uses recorded emails or member additions, not contacts."""
import asyncio
from datetime import datetime
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
def clock(monkeypatch):
    monkeypatch.setattr(performance, "current_time", lambda: NOW)


def call(args=None, scope=None, selected_id=None):
    registry = MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA), selected_id)
    return json.loads(registry.execute("get_campaign_contact_ranking", json.dumps(args or {})))


def row(campaign_id, name, emailed, added, count, campaign_count=2, tie_count=1):
    return {
        "campaign_id": campaign_id, "name": name, "status": "active",
        "campaign_members_total": 10, "clients_emailed": emailed,
        "members_added": added, "count_value": count,
        "campaign_count": campaign_count, "tie_count": tie_count,
    }


def test_schema_exposes_metric_and_period_but_not_scope():
    schemas = MCPToolRegistry(server).schemas()
    schema = next(item["function"]["parameters"] for item in schemas
                  if item["function"]["name"] == "get_campaign_contact_ranking")
    assert set(schema["properties"]) == {"period", "metric"}


def test_default_ranks_cumulative_emailed_clients(monkeypatch):
    def rank(scope, metric, start, end, as_of):
        assert scope.fa_id == DEMO_FA
        assert metric == "clients_emailed"
        assert start is None and end == NOW and as_of == NOW
        return (row("camp-1", "Legacy Protection Refresh", 8, 2, 8),
                row("camp-2", "First Home Starter Bundle", 5, 3, 5))
    monkeypatch.setattr(repository, "rank_campaigns_by_member_metric", rank)
    result = call(selected_id="camp-2")
    assert result["metric"] == "clients_emailed"
    assert result["highest_count"] == 8
    assert result["leaders"][0]["campaign_id"] == "camp-1"
    assert result["ranking_truncated"] is False
    assert "contacted" not in result["summary"]
    assert result["contact_history_available"] is False


def test_weekly_member_ranking_and_ties(monkeypatch):
    def rank(scope, metric, start, end, as_of):
        assert metric == "members_added"
        assert start.isoformat() == "2026-10-05T00:00:00+08:00"
        assert end.isoformat() == "2026-10-12T00:00:00+08:00"
        return (row("camp-1", "Legacy Protection Refresh", 8, 3, 3, tie_count=2),
                row("camp-2", "First Home Starter Bundle", 5, 3, 3, tie_count=2))
    monkeypatch.setattr(repository, "rank_campaigns_by_member_metric", rank)
    result = call({"metric": "members_added", "period": "last_week"})
    assert result["period_start_date"] == "2026-10-05"
    assert result["period_end_date"] == "2026-10-11"
    assert len(result["leaders"]) == 2
    assert "tie" in result["summary"]


def test_weekly_email_ranking_unavailable_and_empty_scope(monkeypatch):
    monkeypatch.setattr(repository, "rank_campaigns_by_member_metric",
                        lambda *_: (_ for _ in ()).throw(AssertionError("must not read")))
    assert call({"period": "this_week"})["error_code"] == "period_unavailable"
    assert call({"period": "last_week"})["error_code"] == "period_unavailable"
    for args in ({"fa_id": DEMO_FA}, {"campaign": "camp-1"}, {"metric": "contacts"}):
        assert call(args)["error"] == "Invalid tool arguments"
    monkeypatch.setattr(repository, "rank_campaigns_by_member_metric", lambda *_: ())
    assert call()["campaign_count"] == 0
    assert call()["leaders"] == []


def test_storage_failure_and_missing_scope(monkeypatch):
    def fail(*_):
        raise repository.CampaignStorageUnavailable("Campaign database is temporarily unavailable")
    monkeypatch.setattr(repository, "rank_campaigns_by_member_metric", fail)
    assert call()["error_code"] == "storage_unavailable"

    async def unscoped():
        async with Client(server) as client:
            return await client.call_tool("get_campaign_contact_ranking", {})
    assert asyncio.run(unscoped()).data["error_code"] == "missing_context"

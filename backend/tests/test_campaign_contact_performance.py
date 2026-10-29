"""Campaign performance reports only facts available from campaign_member."""
import asyncio
from contextlib import nullcontext
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
def campaign_data(campaign_rows, monkeypatch):
    monkeypatch.setattr(performance, "current_time", lambda: NOW)


def call(args=None, scope=None, selected_id=None):
    registry = MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA), selected_id)
    return json.loads(registry.execute("get_campaign_contact_performance", json.dumps(args or {})))


def metrics(*_):
    return {
        "campaign_members_total": 10,
        "clients_emailed_total": 6,
        "email_sends_total": 9,
        "members_added_this_week": 2,
        "members_added_last_week": 3,
        "members_added_requested_week": 4,
    }


def test_model_schema_does_not_accept_adviser_identity():
    schemas = MCPToolRegistry(server).schemas()
    schema = next(item["function"]["parameters"] for item in schemas
                  if item["function"]["name"] == "get_campaign_contact_performance")
    assert set(schema["properties"]) == {"campaign", "period", "week_of"}


def test_selected_campaign_reports_members_and_cumulative_email_only(monkeypatch):
    def read(scope, campaign_id, as_of, week_start, last_start, requested_start, requested_end):
        assert scope.fa_id == DEMO_FA
        assert campaign_id == "camp-1"
        assert as_of == NOW
        assert week_start.isoformat() == "2026-10-12T00:00:00+08:00"
        assert last_start.isoformat() == "2026-10-05T00:00:00+08:00"
        assert requested_start is requested_end is None
        return metrics()
    monkeypatch.setattr(repository, "get_campaign_member_metrics", read)
    result = call({"campaign": "First Home Starter Bundle"}, selected_id="camp-1")
    assert result["campaign_name"] == "Legacy Protection Refresh"
    assert result["campaign_members_total"] == 10
    assert result["clients_emailed_total"] == 6
    assert result["email_sends_total"] == 9
    assert result["email_coverage_percent"] == 60.0
    assert result["members_added_this_week"] == 2
    assert result["contact_history_available"] is False
    assert "contacted_clients_this_week" not in result
    assert "unavailable" in result["summary"]


def test_last_and_specific_week_report_additions_not_contacts(monkeypatch):
    monkeypatch.setattr(repository, "get_campaign_member_metrics", lambda *_: metrics())
    last = call({"period": "last_week"}, selected_id="camp-1")
    assert last["members_added_last_week"] == 3
    assert "3 members were added last week" in last["summary"]
    assert "contacted_clients_last_week" not in last

    def named(scope, campaign_id, as_of, week_start, last_start, requested_start, requested_end):
        assert requested_start.isoformat() == "2026-09-28T00:00:00+08:00"
        assert requested_end.isoformat() == "2026-10-05T00:00:00+08:00"
        return metrics()
    monkeypatch.setattr(repository, "get_campaign_member_metrics", named)
    named_result = call({"period": "specific_week", "week_of": "2026-10-04"},
                        selected_id="camp-1")
    assert named_result["members_added_requested_week"] == 4
    assert named_result["requested_week_start_date"] == "2026-09-28"
    assert named_result["requested_week_end_date"] == "2026-10-04"
    assert "contacted_clients_requested_week" not in named_result


def test_invalid_week_and_scope_fail_closed(monkeypatch):
    monkeypatch.setattr(repository, "get_campaign_member_metrics",
                        lambda *_: (_ for _ in ()).throw(AssertionError("must not read")))
    assert call({"period": "specific_week"}, selected_id="camp-1")["error_code"] == "invalid_arguments"
    assert call({"period": "specific_week", "week_of": "2026-02-30"},
                selected_id="camp-1")["error_code"] == "invalid_arguments"
    assert call({"period": "specific_week", "week_of": "2026-10-20"},
                selected_id="camp-1")["error_code"] == "future_period"
    assert call({"period": "this_week", "week_of": "2026-10-04"},
                selected_id="camp-1")["error_code"] == "invalid_arguments"
    assert call(selected_id="camp-1", scope=RequestScope("adv-other-demo"))["error_code"] == "campaign_unavailable"
    assert call()["error_code"] == "missing_campaign"
    for args in ({"fa_id": DEMO_FA}, {"tenant_id": "pulse-demo"},
                 {"period": "yesterday"}):
        assert call(args)["error"] == "Invalid tool arguments"

    async def unscoped():
        async with Client(server) as client:
            return await client.call_tool("get_campaign_contact_performance",
                                          {"campaign": "camp-1"})
    assert asyncio.run(unscoped()).data["error_code"] == "missing_context"


def test_storage_failure_has_no_counts(monkeypatch):
    def fail(*_):
        raise repository.CampaignStorageUnavailable("Campaign database is temporarily unavailable")
    monkeypatch.setattr(repository, "get_campaign_member_metrics", fail)
    result = call(selected_id="camp-1")
    assert result["error_code"] == "storage_unavailable"
    assert "campaign_members_total" not in result


def test_changing_engagement_status_does_not_increase_email_count(monkeypatch):
    from app.campaigns import catalog

    queries = []

    class Connection:
        def execute(self, query, params):
            queries.append(query)
            return self

        def fetchone(self):
            return {"campaign_member_id": "member-1"}

    monkeypatch.setattr(catalog, "_connection", lambda: nullcontext(Connection()))
    catalog.update_engagement_status(DEMO_FA, "camp-1", "client-1", 1)
    assert len(queries) == 2
    assert "SET engagement_status = %s" in queries[1]
    assert "email_send_count" not in queries[1]

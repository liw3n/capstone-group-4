import pytest

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime
import importlib.util
import json
from pathlib import Path

from fastmcp import Client

pytestmark = pytest.mark.usefixtures("campaign_rows")

from app.campaigns.repository import DEMO_FA, RequestScope
from app.tools import campaign_follow_up as implementations
from app.tools.campaign import execute_recommendation
from app.tools.mcp_registry import MCPToolRegistry

spec = importlib.util.spec_from_file_location(
    "pulse_mcp_server", Path(__file__).parents[1] / "mcp" / "server.py"
)
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)
server = server_module.mcp


def test_schema_exposes_only_campaign_and_bounded_limit():
    schemas = MCPToolRegistry(server).schemas()
    names = {item["function"]["name"] for item in schemas}
    schema = next(item["function"]["parameters"] for item in schemas
                  if item["function"]["name"] == "recommend_clients_for_campaign")
    follow_up_schema = next(
        item["function"]["parameters"]
        for item in schemas
        if item["function"]["name"] == "campaign_follow_up"
    )
    tool_descriptions = {
        item["function"]["name"]: item["function"]["description"]
        for item in schemas
    }
    assert names == {"recommend_clients_for_campaign", "campaign_follow_up",
                     "find_campaign_references", "prepare_campaign_draft",
                     "get_active_campaigns", "get_campaign_contact_performance",
                     "get_campaign_contact_ranking", "prepare_campaign_email",
                     "resolve_campaign"}
    assert "confirm_campaign_email" not in names
    assert set(schema["properties"]) == {"campaign_id", "limit"}
    assert schema["properties"]["limit"]["minimum"] == 1
    assert schema["properties"]["limit"]["maximum"] == 100
    assert set(follow_up_schema["properties"]) == {"campaign", "limit"}
    email_schema = next(
        item["function"]["parameters"] for item in schemas
        if item["function"]["name"] == "prepare_campaign_email"
    )
    assert set(email_schema["properties"]) == {
        "subject", "body", "campaign_id", "recipient_ids"
    }
    assert "fa_id" not in follow_up_schema.get("required", [])
    assert "before outreach" in tool_descriptions["recommend_clients_for_campaign"]
    assert "does not identify" in tool_descriptions["recommend_clients_for_campaign"]
    assert "clients already contacted" in tool_descriptions[
        "recommend_clients_for_campaign"
    ]
    assert "already contacted" in tool_descriptions["campaign_follow_up"]
    assert "not to discover or filter" in tool_descriptions[
        "campaign_follow_up"
    ]
    assert "a pre-contact eligible audience" in tool_descriptions["campaign_follow_up"]


def test_campaign_implementations_read_dict_rows(monkeypatch):
    engagement_date = datetime(2026, 8, 2, 11, 0)

    class FakeResult:
        def __init__(self, row=None, rows=None):
            self.row = row
            self.rows = rows or []

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def execute(self, query, parameters):
            if "SELECT campaign_id" in query:
                assert parameters == ("%Legacy Protection Refresh%",)
                return FakeResult(rows=[{"campaign_id": "camp-1"}])
            assert parameters == ("camp-1", DEMO_FA)
            return FakeResult(rows=[{
                "client_id": "client-002",
                "last_engagement_date": engagement_date,
            }])

    monkeypatch.setattr(
        implementations, "_connection", lambda: nullcontext(FakeConnection())
    )

    assert implementations.get_campaign_id("Legacy Protection Refresh") == "camp-1"
    assert implementations.get_client_follow_up_list("camp-1", DEMO_FA) == [
        ("client-002", engagement_date)
    ]


def test_campaign_follow_up_returns_profiles_with_grounded_reasons(monkeypatch):
    engagement_date = datetime(2026, 8, 2, 11, 0)
    portfolio_requests = []
    profile_requests = []

    def get_campaign(campaign):
        assert campaign == "camp-1"
        return campaign

    def get_clients(campaign_id, fa_id):
        assert campaign_id == "camp-1"
        return [
            ("client-002", engagement_date),
            ("client-003", engagement_date),
        ]

    def get_portfolio(client_id):
        portfolio_requests.append(client_id)
        return {"client_id": client_id, "portfolio_value": 125000}

    def get_profile(client_id):
        profile_requests.append(client_id)
        return {"client_id": client_id, "name": "Demo Client B", "age": 70}

    monkeypatch.setattr(server_module, "get_campaign_id", get_campaign)
    monkeypatch.setattr(server_module, "get_campaign_info", lambda campaign_id: {
        "campaign_id": campaign_id, "campaign_name": "Legacy Protection Refresh",
    })
    monkeypatch.setattr(server_module, "get_client_follow_up_list", get_clients)
    monkeypatch.setattr(server_module, "fetch_client_portfolio", get_portfolio)
    monkeypatch.setattr(server_module, "fetch_client_profile", get_profile)

    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"campaign":"camp-1","limit":1}'
    ))

    assert result["campaign_info"] == {
        "campaign_id": "camp-1", "campaign_name": "Legacy Protection Refresh",
    }
    assert result["total_unreplied_clients"] == 2
    assert result["requested_limit"] == 1
    assert "already been contacted" in result["additional_instructions"]
    assert "not a pre-contact eligible audience" in result["additional_instructions"]
    assert result["candidates"] == [{
        "client_id": "client-002",
        "portfolio_data": {"client_id": "client-002", "portfolio_value": 125000},
        "profile_data": {"client_id": "client-002", "name": "Demo Client B", "age": 70},
        "last_engagement_date": engagement_date.isoformat(),
        "follow_up_reason": (
            "No response is recorded after contact on "
            f"{engagement_date.isoformat()}."
        ),
    }, {
        "client_id": "client-003",
        "portfolio_data": {"client_id": "client-003", "portfolio_value": 125000},
        "profile_data": {"client_id": "client-003", "name": "Demo Client B", "age": 70},
        "last_engagement_date": engagement_date.isoformat(),
        "follow_up_reason": (
            "No response is recorded after contact on "
            f"{engagement_date.isoformat()}."
        ),
    }]
    assert "Give each candidate's follow_up_reason" in result["additional_instructions"]
    assert portfolio_requests == ["client-002", "client-003"]
    assert profile_requests == ["client-002", "client-003"]


def test_campaign_follow_up_prefers_selected_campaign_context(monkeypatch):
    resolved_campaigns = []

    def get_campaign(campaign):
        resolved_campaigns.append(campaign)
        return campaign

    monkeypatch.setattr(server_module, "get_campaign_id", get_campaign)
    monkeypatch.setattr(server_module, "get_campaign_info", lambda _campaign_id: {})
    monkeypatch.setattr(server_module, "get_client_follow_up_list", lambda *_args: [])

    registry = MCPToolRegistry(server).bind_scope(
        RequestScope(DEMO_FA), campaign_id="camp-2"
    )
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"campaign":"Spring Promo"}'
    ))

    assert resolved_campaigns == ["camp-2"]
    assert result["total_unreplied_clients"] == 0


def test_campaign_follow_up_requires_campaign_when_no_selection():
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute("campaign_follow_up", "{}"))

    assert result["error_code"] == "missing_campaign"


def test_campaign_follow_up_requires_server_bound_adviser_context():
    registry = MCPToolRegistry(server)
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"campaign":"camp-1","limit":5}'
    ))

    assert result["error_code"] == "missing_context"


def test_real_mcp_protocol_returns_structured_matches(caplog):
    caplog.set_level("INFO")
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute("recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'))
    assert result["data_source"] == "synthetic"
    assert result["matched_count"] == 4
    assert result["returned_count"] == 4
    assert result["evaluated_count"] == 12
    assert result["clients"][0]["contact_id"] == "client-001"
    assert "MCP tool called: recommend_clients_for_campaign" in caplog.text


def test_tool_requires_metadata_and_checks_access():
    async def direct_call():
        async with Client(server) as client:
            return await client.call_tool("recommend_clients_for_campaign", {"campaign_id": "camp-1"})
    result = asyncio.run(direct_call())
    assert result.data["error_code"] == "missing_context"
    registry = MCPToolRegistry(server).bind_scope(RequestScope("adv-other-demo"))
    result = json.loads(registry.execute("recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'))
    assert result["error_code"] == "campaign_unavailable"
    assert "clients" not in result


def test_model_cannot_inject_identity_or_override_metadata():
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    for extra in ({"fa_id": "adv-other-demo"}, {"tenant_id": "other-demo-tenant"},
                  {"ctx": {}}, {"pulse_scope": {"fa_id": "adv-other-demo"}}):
        args = {"campaign_id": "camp-1", **extra}
        assert json.loads(registry.execute("recommend_clients_for_campaign", json.dumps(args)))["error"] == "Invalid tool arguments"
    for limit in (0, 101, True, 1.5):
        result = json.loads(registry.execute("recommend_clients_for_campaign",
                                            json.dumps({"campaign_id": "camp-1", "limit": limit})))
        assert result["error"] == "Invalid tool arguments"


def test_request_scopes_do_not_leak_between_concurrent_calls():
    base = MCPToolRegistry(server)
    def run(fa_id):
        return json.loads(base.bind_scope(RequestScope(fa_id)).execute(
            "recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        own, other = list(pool.map(run, [DEMO_FA, "adv-other-demo"]))
    assert own["matched_count"] == 4
    assert other["error_code"] == "campaign_unavailable"
    assert base.scope is None


def test_malformed_metadata_fails_closed():
    for metadata in (None, {}, {"pulse_scope": "bad"},
                     {"pulse_scope": {"fa_id": "", "tenant_id": "pulse-demo"}}):
        assert execute_recommendation("camp-1", 100, metadata)["error_code"] == "missing_context"

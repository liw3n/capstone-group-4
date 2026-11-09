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
    assert "discard_campaign_email" not in names
    assert set(schema["properties"]) == {"campaign_id", "limit"}
    assert schema["properties"]["limit"]["minimum"] == 1
    assert schema["properties"]["limit"]["maximum"] == 100
    assert set(follow_up_schema["properties"]) == {"campaign", "limit"}
    email_schema = next(
        item["function"]["parameters"] for item in schemas
        if item["function"]["name"] == "prepare_campaign_email"
    )
    assert set(email_schema["properties"]) == {
            "subject", "body", "campaign_id", "recipient_ids", "signoff_name"
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
            assert parameters == ("camp-1",) + (DEMO_FA,) * 5
            assert "campaign.created_by_user_id = %s" in query
            assert "client.assigned_to_user_id = %s" in query
            return FakeResult(rows=[{
                "client_id": "client-002",
                "last_engagement_date": engagement_date,
            }])

    monkeypatch.setattr(
        implementations, "_connection", lambda: nullcontext(FakeConnection())
    )

    assert implementations.get_client_follow_up_list("camp-1", DEMO_FA) == [
        ("client-002", engagement_date)
    ]


def test_campaign_follow_up_returns_profiles_with_grounded_reasons(monkeypatch):
    engagement_date = datetime(2026, 8, 2, 11, 0)
    portfolio_requests = []
    profile_requests = []

    def get_clients(campaign_id, fa_id, tenant_id):
        assert campaign_id == "camp-1"
        assert fa_id == DEMO_FA and tenant_id == DEMO_FA
        return [
            ("client-002", engagement_date),
            ("client-003", engagement_date),
        ]

    def get_portfolio(client_id):
        portfolio_requests.append(client_id)
        return {"client_id": client_id, "portfolio_value": 125000}

    def get_profile(client_id, fa_id, tenant_id):
        profile_requests.append(client_id)
        assert fa_id == DEMO_FA and tenant_id == DEMO_FA
        return {"client_id": client_id, "name": "Demo Client B", "age": 70}

    monkeypatch.setattr(server_module, "get_campaign_info", lambda campaign_id, *_scope: {
        "campaign_id": campaign_id, "campaign_name": "Legacy Protection Refresh",
    })
    monkeypatch.setattr(server_module, "get_client_follow_up_list", get_clients)
    monkeypatch.setattr(server_module, "fetch_client_portfolio", get_portfolio)
    monkeypatch.setattr(server_module, "fetch_client_profile", get_profile)

    registry = MCPToolRegistry(server).bind_scope(
        RequestScope(DEMO_FA), campaign_id="camp-1"
    )
    result = json.loads(registry.execute("campaign_follow_up", '{"limit":1}'))

    assert result["campaign_info"] == {
        "campaign_id": "camp-1", "campaign_name": "Legacy Protection Refresh",
    }
    assert result["total_unreplied_clients"] == 2
    assert result["requested_limit"] == 1
    assert result["compared_candidates"] == 2
    assert "already been contacted" in result["additional_instructions"]
    assert "not a pre-contact eligible audience" in result["additional_instructions"]
    assert "Compare all 2 candidates and recommend the top 1" in result[
        "additional_instructions"
    ]
    assert result["candidates"] == [{
        "client_id": client_id,
        "portfolio_data": {"client_id": client_id, "portfolio_value": 125000},
        "profile_data": {"client_id": client_id, "name": "Demo Client B", "age": 70},
        "last_engagement_date": engagement_date.isoformat(),
    } for client_id in ("client-002", "client-003")]
    assert "Dynamically formulate and explain" in result["additional_instructions"]
    assert portfolio_requests == ["client-002", "client-003"]
    assert profile_requests == ["client-002", "client-003"]


def test_campaign_follow_up_compares_every_unreplied_client(monkeypatch):
    clients = [
        (f"client-{day:03d}", datetime(2026, 8, day % 28 + 1, 9, 0))
        for day in range(50)
    ] + [("client-never", None)]
    monkeypatch.setattr(server_module, "get_campaign_info", lambda campaign_id, *_scope: {
        "campaign_id": campaign_id,
    })
    monkeypatch.setattr(server_module, "get_client_follow_up_list", lambda *_args: clients)
    monkeypatch.setattr(server_module, "fetch_client_portfolio", lambda client_id: {})
    monkeypatch.setattr(server_module, "fetch_client_profile", lambda client_id, *_scope: {})

    registry = MCPToolRegistry(server).bind_scope(
        RequestScope(DEMO_FA), campaign_id="camp-1"
    )
    result = json.loads(registry.execute("campaign_follow_up", '{"limit":25}'))

    dates = [item["last_engagement_date"] for item in result["candidates"]]
    assert result["total_unreplied_clients"] == 51
    assert result["compared_candidates"] == 51
    assert {item["client_id"] for item in result["candidates"]} == {
        client_id for client_id, _ in clients
    }
    assert dates[0] is None
    assert dates[1:] == sorted(dates[1:])
    assert "Compare all 51 candidates and recommend the top 25" in result[
        "additional_instructions"
    ]


def _record_follow_up_campaign(monkeypatch, resolution=None):
    """Stub storage and record which campaign ID and name lookups were used."""
    calls = {"info": [], "resolve": []}

    def get_info(campaign_id, fa_id, tenant_id):
        assert fa_id == DEMO_FA and tenant_id == DEMO_FA
        calls["info"].append(campaign_id)
        return {"campaign_id": campaign_id}

    def resolve(arguments, metadata):
        assert metadata["pulse_scope"]["fa_id"] == DEMO_FA
        calls["resolve"].append(arguments["campaign_name"])
        return resolution

    monkeypatch.setattr(server_module, "get_campaign_info", get_info)
    monkeypatch.setattr(server_module, "execute_resolve_campaign", resolve)
    monkeypatch.setattr(server_module, "get_client_follow_up_list", lambda *_args: [])
    return calls


def test_campaign_follow_up_uses_selected_campaign_context(monkeypatch):
    calls = _record_follow_up_campaign(monkeypatch)

    registry = MCPToolRegistry(server).bind_scope(
        RequestScope(DEMO_FA), campaign_id="camp-2"
    )
    result = json.loads(registry.execute("campaign_follow_up", "{}"))

    assert calls == {"info": ["camp-2"], "resolve": []}
    assert result["total_unreplied_clients"] == 0


def _scoped_follow_up(monkeypatch, campaign_argument, resolution=None):
    """Run campaign_follow_up scoped to 'Legacy Refresh' (camp-2) with a named campaign."""
    calls = {"resolve": []}
    monkeypatch.setattr(server_module, "get_campaign_info", lambda campaign_id, *_: {
        "campaign_id": campaign_id, "campaign_name": "Legacy Refresh",
    })

    def resolve(arguments, _metadata):
        calls["resolve"].append(arguments["campaign_name"])
        return resolution

    monkeypatch.setattr(server_module, "execute_resolve_campaign", resolve)
    monkeypatch.setattr(server_module, "get_client_follow_up_list", lambda *_args: [])
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA), campaign_id="camp-2")
    result = json.loads(registry.execute(
        "campaign_follow_up", json.dumps({"campaign": campaign_argument})
    ))
    return result, calls


@pytest.mark.parametrize("name", ["Legacy Refresh", "the legacy refresh campaign"])
def test_campaign_follow_up_accepts_scoped_campaign_name(monkeypatch, name):
    result, calls = _scoped_follow_up(monkeypatch, name)

    assert result["campaign_info"]["campaign_id"] == "camp-2"
    assert calls["resolve"] == []


def test_campaign_follow_up_rejects_a_different_named_campaign(monkeypatch):
    result, calls = _scoped_follow_up(monkeypatch, "Spring Promo", {
        "status": "matched", "campaign_id": "camp-9", "name": "Spring Promo",
    })

    assert result["error_code"] == "campaign_scope_mismatch"
    assert result["scoped_campaign"] == "Legacy Refresh"
    assert result["requested_campaign"] == "Spring Promo"
    assert "candidates" not in result
    assert calls["resolve"] == ["Spring Promo"]


def test_campaign_follow_up_rejects_an_unresolvable_named_campaign(monkeypatch):
    result, _ = _scoped_follow_up(monkeypatch, "Ended Promo", {
        "status": "not_found", "candidate_count": 0, "message": "No match",
    })

    assert result["error_code"] == "campaign_scope_mismatch"
    assert "candidates" not in result


def test_campaign_follow_up_accepts_ambiguous_name_that_includes_scope(monkeypatch):
    result, _ = _scoped_follow_up(monkeypatch, "Legacy", {
        "status": "ambiguous", "candidate_count": 2,
        "candidates": [{"campaign_id": "camp-2", "name": "Legacy Refresh"},
                       {"campaign_id": "camp-7", "name": "Legacy Planning"}],
    })

    assert result["campaign_info"]["campaign_id"] == "camp-2"


def test_campaign_follow_up_rejects_a_different_campaign_uuid(monkeypatch):
    result, calls = _scoped_follow_up(monkeypatch, "6f1c2a4e-0b7d-4f7e-9a51-3c2d8e9b1a10")

    assert result["error_code"] == "campaign_scope_mismatch"
    assert calls["resolve"] == []


def test_campaign_follow_up_resolves_named_campaign_without_scope(monkeypatch):
    campaign_uuid = "6f1c2a4e-0b7d-4f7e-9a51-3c2d8e9b1a10"
    calls = _record_follow_up_campaign(monkeypatch, {
        "status": "matched", "campaign_id": campaign_uuid, "name": "Spring Promo",
    })

    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"campaign":"  Spring Promo "}'
    ))

    assert calls == {"info": [campaign_uuid], "resolve": ["Spring Promo"]}
    assert result["campaign_info"] == {"campaign_id": campaign_uuid}
    assert result["total_unreplied_clients"] == 0


def test_campaign_follow_up_uses_uuid_argument_without_name_lookup(monkeypatch):
    campaign_uuid = "6f1c2a4e-0b7d-4f7e-9a51-3c2d8e9b1a10"
    calls = _record_follow_up_campaign(monkeypatch)

    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    registry.execute("campaign_follow_up", json.dumps({"campaign": campaign_uuid}))

    assert calls == {"info": [campaign_uuid], "resolve": []}


def test_campaign_follow_up_requires_campaign_when_no_selection():
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute("campaign_follow_up", "{}"))

    assert result["error_code"] == "missing_campaign"


def test_campaign_follow_up_reports_ambiguous_campaign(monkeypatch):
    calls = _record_follow_up_campaign(monkeypatch, {
        "status": "ambiguous", "candidate_count": 2,
        "candidates": [{"campaign_id": "a", "name": "Promo A"},
                       {"campaign_id": "b", "name": "Promo B"}],
    })
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"campaign":"Promo"}'
    ))

    assert result["error_code"] == "campaign_unavailable"
    assert [item["name"] for item in result["campaign_candidates"]] == ["Promo A", "Promo B"]
    assert "candidates" not in result
    assert calls["info"] == []


def test_campaign_follow_up_reports_unknown_campaign(monkeypatch):
    calls = _record_follow_up_campaign(monkeypatch, {
        "status": "not_found", "candidate_count": 0,
        "message": "No accessible active campaign matches that name.",
    })
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"campaign":"Unknown"}'
    ))

    assert result["error_code"] == "campaign_unavailable"
    assert "candidates" not in result
    assert calls["info"] == []


def test_campaign_follow_up_requires_server_bound_adviser_context():
    registry = MCPToolRegistry(server)
    result = json.loads(registry.execute(
        "campaign_follow_up", '{"limit":5}'
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

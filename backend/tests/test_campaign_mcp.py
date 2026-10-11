import pytest

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path

from fastmcp import Client

pytestmark = pytest.mark.usefixtures("campaign_rows")

from app.campaigns.repository import DEMO_FA, RequestScope
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
    assert names == {"recommend_clients_for_campaign", "campaign_follow_up"}
    assert set(schema["properties"]) == {"campaign_id", "limit"}
    assert schema["properties"]["limit"]["minimum"] == 1
    assert schema["properties"]["limit"]["maximum"] == 100


def test_real_mcp_protocol_returns_structured_matches():
    registry = MCPToolRegistry(server).bind_scope(RequestScope(DEMO_FA))
    result = json.loads(registry.execute("recommend_clients_for_campaign", '{"campaign_id":"camp-1"}'))
    assert result["data_source"] == "synthetic"
    assert result["matched_count"] == 4
    assert result["returned_count"] == 4
    assert result["evaluated_count"] == 12
    assert result["clients"][0]["contact_id"] == "client-001"


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

import asyncio
import json

from fastmcp import Client

from app.campaigns import repository as campaign_repository
from app.campaigns.repository import DEMO_FA, RequestScope
from app.campaigns.reference_repository import CatalogueConfigurationError
from app.tools import campaign_references
from app.tools.mcp_registry import MCPToolRegistry
from test_campaign_mcp import server


def call(arguments, scope=None):
    registry = MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA))
    return json.loads(registry.execute("find_campaign_references", json.dumps(arguments)))


def test_mcp_returns_bounded_matches_token_and_reasons_without_database(monkeypatch):
    def database_access_is_forbidden():
        raise AssertionError("campaign reference retrieval must not access PostgreSQL")

    monkeypatch.setattr(campaign_repository, "_connection", database_access_is_forbidden)
    result = call({
        "objective": "Encourage clients nearing retirement to review income readiness",
        "limit": 2,
    })
    assert result["type"] == "campaign_references"
    assert result["data_source"] == "synthetic_curated_catalogue"
    assert result["returnedCount"] == 2
    assert len(result["references"]) == 2
    assert result["retrievalToken"]
    assert all(item["matchReasons"] for item in result["references"])
    assert not ({"tenantIds", "prohibitedClaims"} & result["references"][0].keys())


def test_mcp_empty_result_and_truncation_are_explicit():
    empty = call({"objective": "Organise a charity fun run for employees next quarter"})
    assert empty["references"] == []
    assert empty["returnedCount"] == 0
    assert empty["truncated"] is False

    truncated = call({
        "objective": ("Retirement protection education property legacy income resilience "
                      "funding mortgage beneficiary healthcare savings readiness"),
        "limit": 1,
    })
    assert truncated["returnedCount"] == 1
    assert truncated["truncated"] is True


def test_mcp_requires_bound_scope_and_rejects_identity_injection():
    unbound = MCPToolRegistry(server)
    assert "context" in json.loads(
        unbound.execute("find_campaign_references", '{"objective":"Retirement income readiness"}')
    )["error"]
    assert json.loads(
        unbound.execute("find_campaign_references", '{"objective":"Retirement income readiness"}')
    )["error_code"] == "missing_context"
    for extra in (
        {"fa_id": "adv-other"}, {"tenant_id": "other"}, {"ctx": {}},
        {"pulse_scope": {"fa_id": "adv-other"}},
    ):
        result = call({"objective": "Retirement income readiness review", **extra})
        assert result["error"] == "Invalid tool arguments"
        assert result["error_code"] == "invalid_arguments"
    for limit in (0, 4, True, 1.5):
        result = call({"objective": "Retirement income readiness review", "limit": limit})
        assert result["error"] == "Invalid tool arguments"
        assert result["error_code"] == "invalid_arguments"


def test_catalogue_failure_is_safe(monkeypatch):
    def fail():
        raise CatalogueConfigurationError("sensitive parser detail")

    monkeypatch.setattr(campaign_references, "get_reference_repository", fail)
    result = call({"objective": "Retirement income readiness review"})
    assert result == {
        "data_source": "synthetic_curated_catalogue",
        "error_code": "catalogue_unavailable",
        "error": "Campaign reference catalogue is unavailable",
    }


def test_direct_mcp_missing_metadata_fails_closed_and_tool_is_read_only():
    async def inspect_and_call():
        async with Client(server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "find_campaign_references", {"objective": "Retirement income readiness"}
            )
            return tools, result

    tools, result = asyncio.run(inspect_and_call())
    tool = next(item for item in tools if item.name == "find_campaign_references")
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert not {"fa_id", "tenant_id", "ctx"} & tool.input_schema["properties"].keys()
    assert result.data["error_code"] == "missing_context"

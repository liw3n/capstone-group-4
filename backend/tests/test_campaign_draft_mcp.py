import asyncio
from datetime import datetime, timedelta, timezone
import json

from fastmcp import Client

from app.campaigns import repository as campaign_repository
from app.campaigns.models import CampaignReferenceQuery
from app.campaigns.reference_repository import (
    CampaignReferenceRepository,
    RetrievalTokenSigner,
    load_catalogue,
)
from app.campaigns.repository import DEMO_FA, RequestScope
from app.tools.campaign_draft import execute_prepare_campaign_draft
from app.tools.mcp_registry import MCPToolRegistry
from test_campaign_mcp import server


OBJECTIVE = "Encourage clients nearing retirement to review income readiness"


def valid_draft():
    return {
        "name": "Retirement Income Readiness Review",
        "description": "Invite clients to review retirement income assumptions.",
        "clientMessage": (
            "This educational invitation is not financial advice. Any next step "
            "requires an individual suitability review with your adviser."
        ),
        "criteria": {
            "ageGroups": ["55to64"],
            "genders": [],
            "cashBands": ["50kTo250k", "250kTo1m"],
        },
        "targetDemographicSummary": (
            "Clients nearing retirement across all genders with available assets."
        ),
        "rationale": {
            "ageGroups": "The retirement transition supports this age group.",
            "genders": "The objective is not gender-specific.",
            "cashBands": "Available assets make these bands a review hypothesis.",
        },
        "assumptions": ["Retirement timing and available assets must be confirmed."],
        "disclaimer": (
            "Educational information only, not financial advice; suitability depends "
            "on individual circumstances and adviser review."
        ),
    }


def registry(scope=None):
    return MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA))


def retrieval(registry_value=None, objective=OBJECTIVE):
    bound = registry_value or registry()
    return json.loads(bound.execute(
        "find_campaign_references", json.dumps({"objective": objective, "limit": 2})
    ))


def prepare_arguments(reference_result, objective=OBJECTIVE, citations=None):
    if citations is None:
        citations = [{
            "referenceId": reference_result["references"][0]["referenceId"],
            "version": reference_result["references"][0]["version"],
        }]
    return {
        "objective": objective,
        "retrievalToken": reference_result["retrievalToken"],
        "referencesUsed": citations,
        "draft": valid_draft(),
    }


def test_prepare_returns_one_typed_uncreated_artifact_without_database(monkeypatch):
    def database_access_is_forbidden():
        raise AssertionError("draft preparation must not access PostgreSQL")

    monkeypatch.setattr(campaign_repository, "_connection", database_access_is_forbidden)
    bound = registry()
    references = retrieval(bound)
    result = json.loads(bound.execute(
        "prepare_campaign_draft", json.dumps(prepare_arguments(references))
    ))

    assert result["type"] == "campaign_draft"
    assert result["data_source"] == "ai_generated"
    assert result["created"] is False
    assert result["requires_adviser_review"] is True
    assert result["validation"]["schema_valid"] is True
    assert result["validation"]["policy_valid"] is True
    assert result["referencesUsed"] == prepare_arguments(references)["referencesUsed"]
    assert not {"draftId", "revision", "status", "tenant_id", "fa_id"} & result.keys()


def test_empty_retrieval_can_prepare_schema_grounded_uncited_draft():
    bound = registry()
    objective = "Organise a charity fun run for employees next quarter"
    references = retrieval(bound, objective)
    assert references["references"] == []
    arguments = prepare_arguments(references, objective, citations=[])
    arguments["draft"]["criteria"] = {"ageGroups": [], "genders": [], "cashBands": []}
    arguments["draft"]["targetDemographicSummary"] = "All ages and all genders, with no cash threshold."
    arguments["draft"]["rationale"] = {
        "ageGroups": "No age restriction.",
        "genders": "No gender restriction.",
        "cashBands": "No cash threshold.",
    }
    result = json.loads(bound.execute("prepare_campaign_draft", json.dumps(arguments)))
    assert result["type"] == "campaign_draft"
    assert result["referencesUsed"] == []


def test_prepare_adds_required_review_language_instead_of_rejecting_draft():
    bound = registry()
    references = retrieval(bound)
    arguments = prepare_arguments(references)
    arguments["draft"]["clientMessage"] = "Please meet your adviser to review your assets."
    arguments["draft"]["disclaimer"] = "Terms and conditions apply."

    result = json.loads(bound.execute("prepare_campaign_draft", json.dumps(arguments)))

    assert result["type"] == "campaign_draft"
    assert result["created"] is False
    assert "does not constitute financial advice" in result["draft"]["clientMessage"]
    assert "does not constitute financial advice" in result["draft"]["disclaimer"]
    assert result["validation"]["warnings"][:2] == [
        "Standard review language was added to clientMessage and requires adviser review.",
        "Standard review language was added to disclaimer and requires adviser review.",
    ]


def test_prepare_rejects_unretrieved_citation_tampering_and_cross_scope():
    own_registry = registry()
    references = retrieval(own_registry)
    arguments = prepare_arguments(references, citations=[{
        "referenceId": "campaign-pattern-not-returned-999", "version": 1
    }])
    result = json.loads(own_registry.execute("prepare_campaign_draft", json.dumps(arguments)))
    assert result["error_code"] == "invalid_reference_citation"
    assert result["created"] is False

    arguments = prepare_arguments(references)
    arguments["retrievalToken"] = arguments["retrievalToken"][:-1] + "x"
    result = execute_prepare_campaign_draft(
        arguments,
        {"pulse_scope": {"fa_id": DEMO_FA, "tenant_id": RequestScope(DEMO_FA).tenant_id}},
    )
    assert result["error_code"] == "invalid_retrieval_token"

    other_registry = registry(RequestScope("adv-other"))
    result = json.loads(other_registry.execute(
        "prepare_campaign_draft", json.dumps(prepare_arguments(references))
    ))
    assert result["error_code"] == "scope_mismatch"


def test_prepare_rejects_expired_token():
    now = [datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)]
    service = CampaignReferenceRepository(
        load_catalogue(),
        RetrievalTokenSigner(b"stage-five-test-secret-value", timedelta(seconds=1)),
        lambda: now[0],
    )
    scope = RequestScope(DEMO_FA)
    reference_result = service.find(CampaignReferenceQuery(objective=OBJECTIVE), scope)
    now[0] += timedelta(seconds=2)
    arguments = {
        "objective": OBJECTIVE,
        "retrievalToken": reference_result.retrievalToken,
        "referencesUsed": [],
        "draft": valid_draft(),
    }
    result = execute_prepare_campaign_draft(
        arguments,
        {"pulse_scope": {"fa_id": scope.fa_id, "tenant_id": scope.tenant_id}},
        service,
    )
    assert result["error_code"] == "expired_retrieval_token"
    assert result["created"] is False


def test_prepare_rejects_invalid_or_unsafe_model_arguments():
    bound = registry()
    references = retrieval(bound)
    arguments = prepare_arguments(references)
    arguments["status"] = "active"
    result = json.loads(bound.execute("prepare_campaign_draft", json.dumps(arguments)))
    assert result["error_code"] == "invalid_draft"

    arguments = prepare_arguments(references)
    arguments["draft"]["description"] = "Guaranteed returns for every client."
    result = json.loads(bound.execute("prepare_campaign_draft", json.dumps(arguments)))
    assert result["error_code"] == "unsupported_claim"
    assert result["field"] == "description"
    assert result["rule"] == "guarantee_claim"
    assert "Guaranteed returns" not in result["error"]


def test_prepare_requires_bound_scope_and_exposes_read_only_schema():
    references = retrieval()
    unbound = MCPToolRegistry(server)
    result = json.loads(unbound.execute(
        "prepare_campaign_draft", json.dumps(prepare_arguments(references))
    ))
    assert result["error_code"] == "missing_context"

    async def inspect_and_call():
        async with Client(server) as client:
            tools = await client.list_tools()
            direct = await client.call_tool(
                "prepare_campaign_draft", prepare_arguments(references)
            )
            return tools, direct

    tools, direct = asyncio.run(inspect_and_call())
    tool = next(item for item in tools if item.name == "prepare_campaign_draft")
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert set(tool.input_schema["properties"]) == {
        "objective", "retrievalToken", "referencesUsed", "draft"
    }
    assert direct.data["error_code"] == "missing_context"


def test_registry_keeps_retrieval_token_and_objective_out_of_model_schema():
    bound = registry()
    tool = next(
        item["function"] for item in bound.schemas()
        if item["function"]["name"] == "prepare_campaign_draft"
    )
    assert set(tool["parameters"]["properties"]) == {"referencesUsed", "draft"}
    assert set(tool["parameters"]["required"]) == {"referencesUsed", "draft"}

    references = retrieval(bound)
    arguments = prepare_arguments(references)
    arguments.pop("objective")
    arguments.pop("retrievalToken")
    result = json.loads(bound.execute("prepare_campaign_draft", json.dumps(arguments)))
    assert result["type"] == "campaign_draft"
    assert result["objective"] == OBJECTIVE

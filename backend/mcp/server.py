import logging
import re
import sys
from pathlib import Path
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

# Direct script execution puts backend/mcp on sys.path; add backend so the shared
# application tool implementations remain importable.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tools.implementations import (
    get_campaign_id,
    get_client_follow_up_list,
    fetch_client_portfolio,
    fetch_client_profile,
    get_campaign_info
)

from app.campaigns.repository import CAMPAIGN_ID_PATTERN
from app.campaigns.models import (
    CampaignCategory,
    CampaignDraft,
    CampaignReferenceCitation,
)
from app.tools.campaign import execute_recommendation
from app.tools.campaign_draft import execute_prepare_campaign_draft
from app.tools.campaign_references import execute_find_campaign_references
from app.tools.discovery import CampaignField, CampaignId, CampaignName, execute_discovery
from app.tools.performance import execute_contact_performance, execute_contact_ranking

# Initialize the FastMCP server instance
mcp = FastMCP(name="FastMCP Server")
logger = logging.getLogger(__name__)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def recommend_clients_for_campaign(
    campaign_id: Annotated[str, Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)],
    ctx: Context,
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 100,
) -> dict:
    """Return synthetic clients meeting campaign criteria, with reasons and gaps.
    Read-only; no ranking or product suitability assessment. Adviser and tenant
    scope come from API request metadata, never from model arguments.
    """
    logger.info("MCP tool called: recommend_clients_for_campaign")
    request = ctx.request_context
    metadata = request.meta if request is not None else None
    if metadata is not None and not isinstance(metadata, dict):
        metadata = metadata.model_dump()
    return execute_recommendation(campaign_id, limit, metadata)

@mcp.tool()
def campaign_follow_up(
    ctx: Context,
    campaign: Annotated[
        str | None,
        Field(description="Campaign name or ID from the current user message. Used only when no campaign is selected."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 5,
) -> dict:
    """
    Return unreplied clients and their detailed portfolio profiles for a given campaign
    so high-value and suitable follow-ups can be identified.
    """
    logger.info("MCP tool called: campaign_follow_up")
    request = ctx.request_context
    metadata = request.meta if request is not None else None
    if metadata is not None and not isinstance(metadata, dict):
        metadata = metadata.model_dump()
    pulse_scope = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    fa_id = pulse_scope.get("fa_id") if isinstance(pulse_scope, dict) else None
    if not isinstance(fa_id, str) or not fa_id.strip():
        return {
            "error": "Adviser request context is required",
            "error_code": "missing_context",
        }

    # 1. Get campaign and unreplied client IDs
    selected_campaign_id = metadata.get("campaign_id") if isinstance(metadata, dict) else None
    if selected_campaign_id is not None:
        if (not isinstance(selected_campaign_id, str)
                or re.fullmatch(CAMPAIGN_ID_PATTERN, selected_campaign_id) is None):
            return {
                "error": "Selected campaign context is invalid",
                "error_code": "invalid_campaign_context",
            }
        campaign_query = selected_campaign_id
    else:
        campaign_query = campaign
    if not isinstance(campaign_query, str) or not campaign_query.strip():
        return {
            "error": "A selected campaign or campaign name from the current message is required",
            "error_code": "missing_campaign",
        }

    campaign_id = get_campaign_id(campaign_query)
    campaign_info = get_campaign_info(campaign_id)
    client_info = get_client_follow_up_list(campaign_id, fa_id)
    limited_client_info = client_info[:limit]

    # 2. Fetch portfolio info for these clients
    client_profiles = []
    for client_id, last_engagement_date in limited_client_info:
        portfolio = fetch_client_portfolio(client_id)
        profile = fetch_client_profile(client_id)
        client_profiles.append({
            "client_id": client_id,
            "portfolio_data": portfolio,
            "profile_data": profile,
            "last_engagement_date": last_engagement_date.isoformat() if last_engagement_date else None
        })

    additional_instructions = (
        "Based on the provided campaign and client information, identify the purpose of the campaign and the target audience for the campaign."
        "Evaluate the customer profile and portfolio to identify the most suitable clients that are high-value to follow-up on for the campaign"
        "to ensure that the campaign is effective and reaches the right audience. " 
        "Note: This tool does not check outreach consent or authorise sending communications; adviser confirmation and separate channel consent checks are required before outreach."
    )

    # 3. Return the rich data back to the LLM
    return {
        "campaign_info": campaign_info,
        "total_unreplied_clients": len(client_info),
        "requested_limit": limit,
        "candidates": client_profiles,
        "additional_instructions": additional_instructions,
    }


def _request_metadata(ctx: Context) -> dict | None:
    request = ctx.request_context
    metadata = request.meta if request is not None else None
    return metadata if metadata is None or isinstance(metadata, dict) else metadata.model_dump()


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def find_campaign_references(
    objective: Annotated[
        str,
        Field(
            min_length=10,
            max_length=2_000,
            description="The adviser's plain-language campaign business objective.",
        ),
    ],
    ctx: Context,
    categories: Annotated[
        list[CampaignCategory] | None,
        Field(max_length=5, description="Optional campaign categories explicitly requested."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=3, strict=True)] = 3,
) -> dict:
    """Find up to three approved synthetic patterns for campaign drafting.

    Read-only: it does not inspect clients, assess suitability, create a draft,
    create a campaign or mutate CRM data. Adviser and tenant scope come only
    from trusted API metadata, never model arguments.
    """
    logger.info("MCP tool called: find_campaign_references")
    return execute_find_campaign_references(
        {"objective": objective, "categories": categories, "limit": limit},
        _request_metadata(ctx),
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def prepare_campaign_draft(
    objective: Annotated[
        str,
        Field(
            min_length=10,
            max_length=2_000,
            description="The same campaign objective used to retrieve references.",
        ),
    ],
    retrievalToken: Annotated[str, Field(min_length=20, max_length=8_000)],
    referencesUsed: Annotated[list[CampaignReferenceCitation], Field(max_length=3)],
    draft: CampaignDraft,
    ctx: Context,
) -> dict:
    """Validate and package one AI-generated campaign draft for adviser review.

    Requires a valid reference-retrieval token and accepts citations only from
    that retrieval result. Read-only: it does not persist, create, activate or
    send a campaign and always returns created=false on success.
    """
    logger.info("MCP tool called: prepare_campaign_draft")
    return execute_prepare_campaign_draft(
        {
            "objective": objective,
            "retrievalToken": retrievalToken,
            "referencesUsed": [item.model_dump() for item in referencesUsed],
            "draft": draft.model_dump(),
        },
        _request_metadata(ctx),
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_active_campaigns(
    ctx: Context,
    campaign_ids: Annotated[list[CampaignId] | None, Field(max_length=100)] = None,
    campaign_names: Annotated[list[CampaignName] | None, Field(max_length=100)] = None,
    fields: Annotated[list[CampaignField] | None, Field(min_length=1, max_length=12)] = None,
    limit: Annotated[int, Field(ge=1, le=1000, strict=True)] = 1000,
) -> dict:
    """List accessible synthetic campaigns active today in Singapore as a table.
    Optional exact IDs/names restrict campaigns (both filters intersect).
    Omit fields unless the user explicitly requests particular details. Defaults:
    campaign_id, name, start_date, end_date, age_groups, genders, cash_bands.
    Name is always included; campaign_id is an allowed output field.
    Active is a filter, not a request to show only status. User identity (fa_id)
    comes only from API metadata. Report empty results and truncation.
    """
    logger.info("MCP tool called: get_active_campaigns")
    return execute_discovery('get_active_campaigns', dict(campaign_ids=campaign_ids,
        campaign_names=campaign_names, fields=fields, limit=limit), _request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_campaign_contact_performance(
    ctx: Context,
    campaign: Annotated[
        str | None,
        Field(description="Exact campaign name or ID from the current message; omit when one is selected.",
              min_length=1, max_length=255),
    ] = None,
    period: Annotated[
        Literal["this_week", "last_week"],
        Field(description="Use last_week for the previous Monday through Sunday in Singapore time; defaults to this_week."),
    ] = "this_week",
) -> dict:
    """Count distinct clients contacted for one accessible synthetic campaign.

    Returns campaign-to-date, current-week and previous-week counts from recorded outreach events.
    Adviser and tenant scope come from API metadata, never model arguments.
    """
    logger.info("MCP tool called: get_campaign_contact_performance")
    return execute_contact_performance({"campaign": campaign, "period": period},
                                       _request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_campaign_contact_ranking(
    ctx: Context,
    period: Annotated[
        Literal["campaign_to_date", "this_week", "last_week"],
        Field(description="Comparison period. Defaults to each campaign's start through now; last_week is the previous Monday through Sunday in Singapore time."),
    ] = "campaign_to_date",
) -> dict:
    """Find which accessible synthetic campaigns contacted the most distinct clients.

    Compare all campaigns available to this adviser, regardless of the selected
    campaign. Counts come only from recorded campaign contact events.
    """
    logger.info("MCP tool called: get_campaign_contact_ranking")
    return execute_contact_ranking({"period": period}, _request_metadata(ctx))


# 3. Run the Server
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="http", host="0.0.0.0", port=8001)

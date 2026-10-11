import logging
import re
import sys
from pathlib import Path
from typing import Annotated

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
from app.tools.campaign import execute_recommendation

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


# 3. Run the Server
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="http", host="0.0.0.0", port=8001)

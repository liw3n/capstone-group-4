import logging
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
    fetch_client_profile
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
    campaign: Annotated[
        str,
        Field(description="The identifier for the campaign. Can be either the campaign name (e.g., 'Spring Promo') or the campaign ID (e.g., 'camp-12345').")
    ],
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 5,
) -> dict:
    """
    Return unreplied clients and their detailed portfolio profiles for a given campaign
    so high-value follow-ups can be identified.
    """
    logger.info("MCP tool called: campaign_follow_up")
    # 1. Get campaign and unreplied client IDs
    campaign_id = get_campaign_id(campaign)
    client_info = get_client_follow_up_list(campaign_id)
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

    # 3. Return the rich data back to the LLM
    return {
        "campaign_name": campaign,
        "total_unreplied_clients": len(client_info),
        "requested_limit": limit,
        "candidates": client_profiles
    }


# 3. Run the Server
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="http", host="0.0.0.0", port=8001)

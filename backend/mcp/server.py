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
    calculate_sum as calculate_sum_impl,
    search_database as search_database_impl,
)

from app.campaigns.repository import CAMPAIGN_ID_PATTERN
from app.tools.campaign import execute_recommendation

# Initialize the FastMCP server instance
mcp = FastMCP(name="FastMCP Server")


# Register a Tool using the @mcp.tool decorator
@mcp.tool()
def search_database(query: str, limit: int = 5) -> dict:
    """Search campaign data (placeholder implementation)."""
    return search_database_impl(query, limit)


@mcp.tool()
def calculate_sum(a: float, b: float) -> float:
    """Adds two numbers together."""
    return calculate_sum_impl(a, b)


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
    request = ctx.request_context
    metadata = request.meta if request is not None else None
    if metadata is not None and not isinstance(metadata, dict):
        metadata = metadata.model_dump()
    return execute_recommendation(campaign_id, limit, metadata)


# 3. Run the Server
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)

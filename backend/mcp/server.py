import sys
from pathlib import Path

from fastmcp import FastMCP

# Direct script execution puts backend/mcp on sys.path; add backend so the shared
# application tool implementations remain importable.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tools.implementations import (
    calculate_sum as calculate_sum_impl,
    search_database as search_database_impl,
)

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


# 3. Run the Server
if __name__ == "__main__":
    # Runs over standard I/O by default (stdio)
    mcp.run()

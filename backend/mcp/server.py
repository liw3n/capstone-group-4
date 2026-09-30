from fastmcp import FastMCP

# Initialize the FastMCP server instance
mcp = FastMCP(name="FastMCP Server")


# Register a Tool using the @mcp.tool decorator
@mcp.tool()
def search_database(query: str, limit: int = 5) -> dict:
    """Searches the local database for relevant entries.
    
    FastMCP automatically generates the JSON tool schema 
    from the type hints and docstring above!
    """
    # Replace this with your actual DB query logic
    return {
        "status": "success",
        "query": query,
        "results": [f"Result #{i + 1} for '{query}'" for i in range(limit)]
    }


@mcp.tool()
def calculate_sum(a: float, b: float) -> float:
    """Adds two numbers together."""
    return a + b


# 3. Run the Server
if __name__ == "__main__":
    # Runs over standard I/O by default (stdio)
    mcp.run()
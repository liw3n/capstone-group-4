def calculate_sum(a: float, b: float) -> float:
    """Return the sum of two numbers."""
    return a + b


def search_database(query: str, limit: int = 5) -> dict:
    """Temporary search tool used until the campaign data source is connected."""
    return {
        "status": "placeholder",
        "query": query,
        "results": [f"Result #{index + 1} for '{query}'" for index in range(limit)],
    }

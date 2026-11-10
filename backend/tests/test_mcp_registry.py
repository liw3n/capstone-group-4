import json

from fastmcp import FastMCP

from app.tools.mcp_registry import MCPToolRegistry, _compact_schema


def test_discovers_and_calls_tools_through_mcp_protocol():
    server = FastMCP("test")

    @server.tool()
    def calculate_sum(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    @server.tool()
    def get_active_campaigns() -> list:
        """A test version of an approved read-only tool."""
        return []

    registry = MCPToolRegistry(server)

    schemas = registry.schemas()
    result = json.loads(registry.execute("calculate_sum", '{"a": 2, "b": 3}'))

    assert [item["function"]["name"] for item in schemas] == ["get_active_campaigns"]
    assert "5" in json.dumps(result)


def test_compact_schema_merges_null_branches_and_drops_noise():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ids": {"anyOf": [{"type": "array", "maxItems": 5,
                               "items": {"type": "string", "pattern": "^[a-z]+$"}},
                              {"type": "null"}], "default": None},
            "period": {"anyOf": [{"type": "string", "enum": ["this_week", "last_week"]},
                                 {"type": "null"}], "default": None},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
    }

    assert _compact_schema(schema) == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ids": {"type": ["array", "null"], "maxItems": 5, "items": {"type": "string"}},
            "period": {"type": ["string", "null"], "enum": ["this_week", "last_week", None]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
    }

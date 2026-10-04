import json

from fastmcp import FastMCP

from app.tools.mcp_registry import MCPToolRegistry


def test_discovers_and_calls_tools_through_mcp_protocol():
    server = FastMCP("test")

    @server.tool()
    def calculate_sum(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    registry = MCPToolRegistry(server)

    schemas = registry.schemas()
    result = json.loads(registry.execute("calculate_sum", '{"a": 2, "b": 3}'))

    assert schemas[0]["function"]["name"] == "calculate_sum"
    assert schemas[0]["function"]["parameters"]["properties"].keys() == {"a", "b"}
    assert "5" in json.dumps(result)
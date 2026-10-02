import json

from app.tools import DEFAULT_TOOL_REGISTRY


def test_calculate_sum():
    result = json.loads(
        DEFAULT_TOOL_REGISTRY.execute("calculate_sum", '{"a": 1.25, "b": 2.75}')
    )
    assert result == {"result": 4.0}


def test_unknown_tool_returns_structured_error():
    result = json.loads(DEFAULT_TOOL_REGISTRY.execute("not_registered", "{}"))
    assert result == {"error": "Unknown tool: not_registered"}


def test_invalid_arguments_do_not_execute_tool():
    result = json.loads(
        DEFAULT_TOOL_REGISTRY.execute("calculate_sum", '{"a": 1, "unexpected": 2}')
    )
    assert result["error"] == "Invalid tool arguments"


def test_schemas_disallow_additional_properties():
    schemas = DEFAULT_TOOL_REGISTRY.schemas()
    calculator = next(
        tool for tool in schemas if tool["function"]["name"] == "calculate_sum"
    )
    assert calculator["function"]["parameters"]["additionalProperties"] is False

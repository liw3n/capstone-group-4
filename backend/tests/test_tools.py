import json

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import ToolDefinition, ToolRegistry


class CalculateSumArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float = Field(description="The first number to add.")
    b: float = Field(description="The second number to add.")


def calculate_sum(a: float, b: float) -> float:
    return a + b


@pytest.fixture
def tool_registry():
    return ToolRegistry([
        ToolDefinition(
            name="calculate_sum",
            description="Add two numbers.",
            arguments_model=CalculateSumArguments,
            handler=calculate_sum,
        )
    ])


def test_calculate_sum(tool_registry):
    result = json.loads(
        tool_registry.execute("calculate_sum", '{"a": 1.25, "b": 2.75}')
    )
    assert result == {"result": 4.0}


def test_unknown_tool_returns_structured_error(tool_registry):
    result = json.loads(tool_registry.execute("not_registered", "{}"))
    assert result == {"error": "Unknown tool: not_registered"}


def test_invalid_arguments_do_not_execute_tool(tool_registry):
    result = json.loads(
        tool_registry.execute("calculate_sum", '{"a": 1, "unexpected": 2}')
    )
    assert result["error"] == "Invalid tool arguments"


def test_schemas_disallow_additional_properties(tool_registry):
    schemas = tool_registry.schemas()
    calculator = next(
        tool for tool in schemas if tool["function"]["name"] == "calculate_sum"
    )
    assert calculator["function"]["parameters"]["additionalProperties"] is False

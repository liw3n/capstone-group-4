import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.implementations import calculate_sum, search_database


class CalculateSumArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float = Field(description="The first number to add.")
    b: float = Field(description="The second number to add.")


class SearchDatabaseArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="The text to search for.")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum result count.")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[..., Any]

    def as_openai_tool(self) -> dict[str, Any]:
        parameters = self.arguments_model.model_json_schema()
        parameters["additionalProperties"] = False
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition] | None = None) -> None:
        self._definitions = {
            definition.name: definition for definition in (definitions or [])
        }

    def schemas(self) -> list[dict[str, Any]]:
        return [definition.as_openai_tool() for definition in self._definitions.values()]

    def execute(self, name: str, arguments_json: str) -> str:
        definition = self._definitions.get(name)
        if definition is None:
            return json.dumps({"error": f"Unknown tool: {name}"})

        try:
            raw_arguments = json.loads(arguments_json)
            arguments = definition.arguments_model.model_validate(raw_arguments)
            result = definition.handler(**arguments.model_dump())
            return json.dumps({"result": result}, default=str)
        except (json.JSONDecodeError, ValidationError) as exc:
            return json.dumps({"error": "Invalid tool arguments", "details": str(exc)})
        except Exception:  # Do not leak tool internals or connection details to the model.
            return json.dumps({"error": "Tool execution failed"})


DEFAULT_TOOL_REGISTRY = ToolRegistry(
    [
        ToolDefinition(
            name="calculate_sum",
            description="Add two numbers and return their sum.",
            arguments_model=CalculateSumArguments,
            handler=calculate_sum,
        ),
        ToolDefinition(
            name="search_database",
            description=(
                "Search the campaign database. This is currently a placeholder tool "
                "for integration testing and does not return production data."
            ),
            arguments_model=SearchDatabaseArguments,
            handler=search_database,
        ),
    ]
)

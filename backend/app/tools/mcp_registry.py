import asyncio
import json
from typing import Any

from fastmcp import Client

from app.llm.errors import LLMProviderError


class MCPToolRegistry:
    def __init__(self, transport: Any, timeout_seconds: float = 30.0) -> None:
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    async def _list_tools(self) -> list[Any]:
        async with Client(self.transport, timeout=self.timeout_seconds) as client:
            return await client.list_tools()

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with Client(self.transport, timeout=self.timeout_seconds) as client:
            return await client.call_tool(name, arguments)

    def schemas(self) -> list[dict[str, Any]]:
        try:
            tools = asyncio.run(self._list_tools())
        except Exception as exc:
            raise LLMProviderError("Could not connect to the MCP tool server") from exc

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def execute(self, name: str, arguments_json: str) -> str:
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid tool arguments"})
        if not isinstance(arguments, dict):
            return json.dumps({"error": "Invalid tool arguments"})

        try:
            result = asyncio.run(self._call_tool(name, arguments))
        except Exception as exc:
            raise LLMProviderError("Could not call the MCP tool server") from exc

        structured_content = getattr(result, "structuredContent", None)
        if structured_content is not None:
            return json.dumps(structured_content, default=str)

        content = [
            getattr(item, "text", str(item))
            for item in getattr(result, "content", [])
        ]
        if getattr(result, "isError", False):
            return json.dumps({"error": content})
        return json.dumps({"result": content})
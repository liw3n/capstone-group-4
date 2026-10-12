import asyncio
import json
from typing import Any

from fastmcp import Client

from pydantic import ValidationError

from app.campaigns.repository import RequestScope
from app.llm.errors import LLMProviderError
from app.tools.campaign import RecommendationArguments
from app.tools.discovery import ActiveCampaignArguments
from app.tools.performance import ContactPerformanceArguments, ContactRankingArguments


class MCPToolRegistry:
    def __init__(self, transport: Any, timeout_seconds: float = 30.0,
                 scope: RequestScope | None = None,
                 campaign_id: str | None = None) -> None:
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.scope = scope
        self.campaign_id = campaign_id

    def bind_scope(
        self, scope: RequestScope, campaign_id: str | None = None
    ) -> "MCPToolRegistry":
        # The cached orchestrator never stores mutable per-adviser context.
        return MCPToolRegistry(self.transport, self.timeout_seconds, scope, campaign_id)

    async def _list_tools(self) -> list[Any]:
        async with Client(self.transport, timeout=self.timeout_seconds) as client:
            return await client.list_tools()

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with Client(self.transport, timeout=self.timeout_seconds) as client:
            metadata = None
            if self.scope is not None:
                metadata = {"pulse_scope": {"fa_id": self.scope.fa_id,
                                            "tenant_id": self.scope.tenant_id}}
                if self.campaign_id is not None:
                    metadata["campaign_id"] = self.campaign_id
            return await client.call_tool(name, arguments, meta=metadata, raise_on_error=False)

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

        if name == "recommend_clients_for_campaign":
            if self.scope is None:
                return json.dumps({"error": "Adviser request context is required"})
            try:
                arguments = RecommendationArguments.model_validate(arguments).model_dump()
            except ValidationError:
                return json.dumps({"error": "Invalid tool arguments"})

        if name == "get_active_campaigns":
            if self.scope is None:
                return json.dumps({"error": "Adviser request context is required"})
            try:
                arguments = ActiveCampaignArguments.model_validate(arguments).model_dump()
            except ValidationError:
                return json.dumps({"error": "Invalid tool arguments"})

        if name == "get_campaign_contact_performance":
            if self.scope is None:
                return json.dumps({"error": "Adviser request context is required"})
            try:
                arguments = ContactPerformanceArguments.model_validate(arguments).model_dump()
            except ValidationError:
                return json.dumps({"error": "Invalid tool arguments"})

        if name == "get_campaign_contact_ranking":
            if self.scope is None:
                return json.dumps({"error": "Adviser request context is required"})
            try:
                arguments = ContactRankingArguments.model_validate(arguments).model_dump()
            except ValidationError:
                return json.dumps({"error": "Invalid tool arguments"})

        try:
            result = asyncio.run(self._call_tool(name, arguments))
        except Exception as exc:
            raise LLMProviderError("Could not call the MCP tool server") from exc

        structured_content = getattr(result, "structured_content", getattr(result, "structuredContent", None))
        if structured_content is not None:
            return json.dumps(structured_content, default=str)

        content = [
            getattr(item, "text", str(item))
            for item in getattr(result, "content", [])
        ]
        if getattr(result, "is_error", getattr(result, "isError", False)):
            return json.dumps({"error": content})
        return json.dumps({"result": content})

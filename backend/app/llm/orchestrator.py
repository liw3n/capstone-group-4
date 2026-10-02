from typing import Any

from app.config import Settings
from app.llm.errors import LLMProviderError, LLMToolLoopError
from app.store import ChatHistoryItem
from app.tools import DEFAULT_TOOL_REGISTRY, ToolRegistry


SYSTEM_PROMPT = """You are PULSE, an assistant for financial advisers.
Use the available tools when they are needed to answer accurately. Never claim that a
placeholder tool returned real production data. Keep answers concise and actionable.
"""


class ChatOrchestrator:
    def __init__(
        self,
        client: Any,
        settings: Settings,
        registry: ToolRegistry = DEFAULT_TOOL_REGISTRY,
    ) -> None:
        self.client = client
        self.settings = settings
        self.registry = registry

    def run(self, user_message: str, history: list[ChatHistoryItem]) -> str:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in history[-self.settings.llm_history_limit :]:
            messages.append(
                {
                    "role": "assistant" if item.user is False else "user",
                    "content": item.message_content,
                }
            )
        messages.append({"role": "user", "content": user_message})

        tools = self.registry.schemas()
        for _ in range(self.settings.llm_max_tool_rounds):
            completion = self.client.create_chat_completion(messages, tools)
            if not getattr(completion, "choices", None):
                raise LLMProviderError("LLM provider returned no choices")

            message = completion.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                content = getattr(message, "content", None)
                if not content:
                    raise LLMProviderError("LLM provider returned an empty answer")
                return content

            messages.append(
                {
                    "role": "assistant",
                    "content": getattr(message, "content", None),
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                result = self.registry.execute(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        raise LLMToolLoopError("LLM exceeded the configured tool-call round limit")

import json
from typing import Any, Protocol

from app.campaigns.repository import RequestScope
from app.config import Settings
from app.llm.errors import LLMProviderError, LLMToolLoopError
from app.store import ChatHistoryItem


SYSTEM_PROMPT = """You are PULSE, an assistant for financial advisers.
Use the available tools when they are needed to answer accurately. Never claim that a
placeholder or synthetic tool returned real production data. Keep answers concise and actionable.

For campaign client recommendations, call recommend_clients_for_campaign and base
names, counts and eligibility explanations only on its output. Return all matches by
default, without inventing a suitability ranking. Report missing information and
exclusions separately. If results are truncated, say so. The current selected
campaign context overrides campaign references in older conversation history.
If no campaign is selected or named, ask the adviser to select one; do not guess.
If a tool returns an error, explain it without inventing client results.
Synthetic criteria matches are not a product suitability assessment or financial
advice. State this when giving recommendations. This read-only tool does not check
outreach consent or authorise sending communications; adviser confirmation and
separate channel consent checks are required before outreach.

For campaign follow-up, call campaign_follow_up to get unreplied clients and their
portfolio profiles. Use this to do a suitability assessment and identify high-value follow-ups. 
Do not invent client results. If a tool returns an error, explain it without inventing client results.
Use the currently selected campaign context when one is provided. Otherwise use
the campaign named in the current user message; if none is named, ask which
campaign they mean rather than guessing.
"""

# Add discovery guidance without replacing the recommendation/follow-up prompt.
SYSTEM_PROMPT += """
For active campaign discovery, call get_active_campaigns. This operation can list
all accessible active campaigns without a selected campaign; the instructions above
requiring a named/selected campaign apply to recommendation and follow-up tools.
Use exact campaign IDs/names only when the current user requests particular campaigns.
Do not narrow a general listing to the currently selected campaign or old history.
Set fields only when the latest user explicitly requests particular details;
otherwise omit fields or use null for campaign_id, name, start_date, end_date,
age_groups, genders, cash_bands. Active is a filter, not a status-only projection.
Campaign discovery uses today's Singapore date for active status;
the existing recommendation tool retains its fixed demo date.
Display the returned Markdown table in full, preserving its values and readable
headers with spaces (Campaign ID, Name, Start Date, etc.).
Campaign IDs are allowed in discovery output; names must also be shown. State
empty results, disclose truncation and label synthetic data. Campaign details are
for adviser review, not a product suitability assessment or financial advice.
Do not interpret discovery as checking consent or authorising communications.
"""

SYSTEM_PROMPT += """
For campaign contact performance questions, call get_campaign_contact_performance.
Use its exact counts, reporting date and campaign state; do not estimate from
recommendations or follow-up lists. The currently selected campaign takes
precedence; otherwise use only the campaign named in the latest user message.
If neither is available, ask which campaign they mean. Distinct clients contacted
this week may include clients first contacted earlier and contacted again this
week. Copy the tool's short summary when it directly answers the question.
Label these results as synthetic prototype data. If the tool returns an error,
explain it without inventing figures. Never reveal another adviser's client
relationship or imply that a missing campaign belongs to someone else.
"""

class ToolExecutor(Protocol):
    def bind_scope(
        self, scope: RequestScope, campaign_id: str | None = None
    ) -> "ToolExecutor": ...

    def schemas(self) -> list[dict[str, Any]]: ...

    def execute(self, name: str, arguments_json: str) -> str: ...


class ChatOrchestrator:
    def __init__(
        self,
        client: Any,
        settings: Settings,
        registry: ToolExecutor,
    ) -> None:
        self.client = client
        self.settings = settings
        self.registry = registry

    def run(self, user_message: str, history: list[ChatHistoryItem], *,
            scope: RequestScope | None = None, campaign_id: str | None = None) -> str:
        registry = (
            self.registry.bind_scope(scope, campaign_id)
            if scope is not None
            else self.registry
        )
        prompt = SYSTEM_PROMPT
        if scope is not None:
            prompt += "\nCurrent campaign context (server-validated): " + json.dumps(
                {"campaign_id": campaign_id, "data_source": "synthetic"}
            )
        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
        for item in history[-self.settings.llm_history_limit :]:
            messages.append(
                {
                    "role": "assistant" if item.user is False else "user",
                    "content": item.message_content,
                }
            )
        messages.append({"role": "user", "content": user_message})

        tools = registry.schemas()
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
                result = registry.execute(
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

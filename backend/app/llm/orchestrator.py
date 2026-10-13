from copy import deepcopy
import json
import re
from typing import Any, Protocol

from pydantic import ValidationError

from app.campaigns.models import CampaignDraftArtifact
from app.campaigns.presentation import render_campaign_draft
from app.campaigns.repository import RequestScope
from app.config import Settings
from app.llm.errors import LLMProviderError, LLMToolLoopError
from app.store import ChatHistoryItem


SYSTEM_PROMPT = """You are PULSE, an assistant for financial advisers.
Use the available tools when they are needed to answer accurately. Never claim that a
placeholder or synthetic tool returned real production data. Keep answers concise and actionable.

Choose campaign client tools by the stage of the workflow requested in the latest
user message:
- Before contact: when finding, filtering, or reviewing clients who meet campaign
  criteria as a potential audience, call recommend_clients_for_campaign. This
  returns criteria matches, not a list of clients already contacted or their
  response status.
- After contact: when finding clients already contacted for the campaign who have
  not replied/responded, or asking who needs a post-contact follow-up, call
  campaign_follow_up. Its candidates are already-contacted clients with no
  recorded response; it is not for finding a new eligible audience.
These tools are not interchangeable. Do not call campaign_follow_up for
pre-contact audience filtering, and do not call recommend_clients_for_campaign
to identify contacted clients awaiting a reply. If the requested workflow stage
is unclear, ask whether the adviser wants a pre-contact eligible audience or an
after-contact no-reply list. Call both only when the adviser explicitly requests
both stages.

For recommendations, base names, counts and eligibility explanations only on
recommend_clients_for_campaign output. Return all matches by default, without
inventing a suitability ranking. Report missing information and exclusions
separately. If results are truncated, say so. The current selected campaign
context overrides campaign references in older conversation history. If no
campaign is selected or named, ask the adviser to select one; do not guess.
If a tool returns an error, explain it without inventing client results.
Synthetic criteria matches are not a product suitability assessment or financial
advice. State this when giving recommendations. This read-only tool does not check
outreach consent or authorise sending communications; adviser confirmation and
separate channel consent checks are required before outreach.

For post-contact follow-up results, use only the returned contacted/no-response
candidates. Explain why each is listed using its follow_up_reason and last contact
date. Use the profile and portfolio details along with the campaign details to infer
suitability, priority or likely response. Do not add criteria-matched clients or describe candidates 
as a fresh audience. Do not invent client results. If a tool returns an error, explain it
without inventing client results. Use the currently selected campaign context
when one is provided. Otherwise use the campaign named in the current user
message; if none is named, ask which campaign they mean rather than guessing.
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
For questions comparing which campaign has the most clients contacted, call
get_campaign_contact_ranking. A question like "which campaign has the highest
number of clients?" means distinct clients contacted in this performance
context. Use campaign_to_date unless the user asks for this week or last week.
Compare every campaign available to the adviser, even when one campaign is
selected in the UI. Name ties, use exact counts, and label the data synthetic.
Do not use the single-campaign performance tool to answer a cross-campaign
comparison. Do not describe these counts as target audience size or sales.

For campaign contact performance questions, call get_campaign_contact_performance.
When the latest question says "last week", set period to "last_week"; this means
the previous Monday through Sunday in Singapore time. Use the tool's last-week
count and dates in the answer. For "this week", use period "this_week".
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

SYSTEM_PROMPT += """
For requests to generate, draft or propose a new campaign from a business
objective, first call find_campaign_references with the objective from the latest user
message. After retrieval, the server requests a schema-constrained draft and
invokes prepare_campaign_draft itself with the retained objective and signed
token. referencesUsed must contain only reference IDs and versions returned by
that retrieval call; it may be empty when no reference was relevant. Generate
every required structured field, make assumptions explicit, explain each
targeting dimension and include educational, individual-review language in both
the client message and disclaimer. Do not invent rates, returns, guarantees,
regulatory approval, client details or unsupported targeting precision.

The preparation tool validates and packages content; it does not save or create
a campaign. Never claim the campaign was created, activated, approved or sent.
The server renders a successful campaign_draft directly. If retrieval fails, do
not fabricate a draft outside the tool.
"""


def _prepared_campaign_draft(result: str) -> CampaignDraftArtifact | None:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("Campaign draft tool returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("type") != "campaign_draft":
        return None
    try:
        return CampaignDraftArtifact.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError("Campaign draft tool returned an invalid artifact") from exc


def _is_campaign_reference_result(result: str) -> bool:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("type") == "campaign_references"


def _campaign_reference_context(result: str) -> str:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("Campaign reference tool returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("type") != "campaign_references":
        raise LLMProviderError("Campaign reference tool returned an invalid result")
    payload.pop("retrievalToken", None)
    return json.dumps(payload, separators=(",", ":"))


def _campaign_reference_failure(result: str) -> str:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("Campaign reference tool returned invalid JSON") from exc
    message = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(message, str):
        raise LLMProviderError("Campaign reference tool returned an invalid result")
    return (
        "## Campaign draft could not be prepared\n\n"
        f"**Reference retrieval issue:** {message}\n\n"
        "No campaign was created."
    )


def _is_campaign_generation_request(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return bool(
        re.search(
            r"\b(?:create|generate|draft|propose|design|build|launch|run)\b"
            r".{0,100}\bcampaign\b",
            normalized,
        )
        or re.search(
            r"\bcampaign\b.{0,100}\b(?:idea|objective|proposal|draft)\b",
            normalized,
        )
    )


def _strict_campaign_generation_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt the model-facing preparation schema for Groq strict JSON output."""
    supported_keys = {
        "type", "properties", "required", "additionalProperties", "items",
        "enum", "description",
    }

    def supported(value: Any) -> Any:
        if isinstance(value, list):
            return [supported(item) for item in value]
        if not isinstance(value, dict):
            return value
        cleaned = {}
        for key, item in value.items():
            if key == "properties" and isinstance(item, dict):
                cleaned[key] = {
                    property_name: supported(property_schema)
                    for property_name, property_schema in item.items()
                }
            elif key in supported_keys:
                cleaned[key] = supported(item)
        return cleaned

    strict_schema = supported(deepcopy(schema))
    draft_schema = strict_schema["properties"]["draft"]
    draft_schema["required"] = list(draft_schema["properties"])
    rationale_properties = {
        dimension: {
            "type": "string",
            "description": f"Rationale for the {dimension} targeting choice.",
        }
        for dimension in ("ageGroups", "genders", "cashBands")
    }
    draft_schema["properties"]["rationale"] = {
        "type": "object",
        "properties": rationale_properties,
        "required": list(rationale_properties),
        "additionalProperties": False,
    }
    return strict_schema


def _campaign_draft_failure(result: str) -> str:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("Campaign draft tool returned invalid JSON") from exc
    message = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(message, str):
        raise LLMProviderError("Campaign draft tool returned an invalid result")
    field = payload.get("field")
    rule = payload.get("rule")
    diagnostic = ""
    if isinstance(field, str) and isinstance(rule, str):
        diagnostic = f"\n\n**Field:** `{field}`  \n**Rule:** `{rule}`"
    return (
        "## Campaign draft could not be prepared\n\n"
        f"**Validation issue:** {message}{diagnostic}\n\n"
        "No campaign was created. Revise the objective or generated content and try again."
    )


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

    def _generate_campaign_draft(
        self,
        *,
        registry: ToolExecutor,
        prompt: str,
        user_message: str,
        reference_result: str,
        preparation_tool: dict[str, Any],
    ) -> str:
        generation_messages = [
            {
                "role": "system",
                "content": (
                    prompt
                    + "\nReturn only the schema-constrained campaign draft. "
                    "Use only the supplied reference IDs and versions."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Business objective:\n{user_message}\n\n"
                    "Retrieved synthetic campaign references:\n"
                    + _campaign_reference_context(reference_result)
                ),
            },
        ]
        generation = self.client.create_structured_completion(
            generation_messages,
            _strict_campaign_generation_schema(
                preparation_tool["function"]["parameters"]
            ),
        )
        if not getattr(generation, "choices", None):
            raise LLMProviderError("LLM provider returned no choices")
        content = getattr(generation.choices[0].message, "content", None)
        if not content:
            raise LLMProviderError("LLM provider returned an empty campaign draft")
        prepared = registry.execute("prepare_campaign_draft", content)
        artifact = _prepared_campaign_draft(prepared)
        if artifact is not None:
            return render_campaign_draft(artifact)
        return _campaign_draft_failure(prepared)

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

        schemas = registry.schemas()
        preparation_tool = next(
            (
                tool for tool in schemas
                if tool.get("function", {}).get("name") == "prepare_campaign_draft"
            ),
            None,
        )
        tools = [
            tool for tool in schemas
            if tool.get("function", {}).get("name") != "prepare_campaign_draft"
        ]
        if _is_campaign_generation_request(user_message):
            if preparation_tool is None:
                raise LLMProviderError("Campaign preparation schema is unavailable")
            reference_result = registry.execute(
                "find_campaign_references",
                json.dumps({"objective": user_message, "limit": 3}),
            )
            if not _is_campaign_reference_result(reference_result):
                return _campaign_reference_failure(reference_result)
            return self._generate_campaign_draft(
                registry=registry,
                prompt=prompt,
                user_message=user_message,
                reference_result=reference_result,
                preparation_tool=preparation_tool,
            )
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
                if tool_call.function.name == "prepare_campaign_draft":
                    artifact = _prepared_campaign_draft(result)
                    if artifact is not None:
                        return render_campaign_draft(artifact)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
                if (
                    tool_call.function.name == "find_campaign_references"
                    and _is_campaign_reference_result(result)
                ):
                    if preparation_tool is None:
                        raise LLMProviderError("Campaign preparation schema is unavailable")
                    return self._generate_campaign_draft(
                        registry=registry,
                        prompt=prompt,
                        user_message=user_message,
                        reference_result=result,
                        preparation_tool=preparation_tool,
                    )

        raise LLMToolLoopError("LLM exceeded the configured tool-call round limit")

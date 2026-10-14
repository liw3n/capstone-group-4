from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from app.config import Settings
from app.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)


class LLMClient:
    """Small provider-neutral wrapper around an OpenAI-compatible client."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        if client is not None:
            self._client = client
            return

        if not settings.llm_configured:
            raise LLMConfigurationError("GROQ_API_KEY is not configured")

        self._client = OpenAI(
            api_key=settings.groq_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        return self._create_completion(
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

    def create_structured_completion(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        schema_name: str = "campaign_draft_generation",
    ) -> Any:
        return self._create_completion(
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )

    def _create_completion(self, **kwargs: Any) -> Any:
        try:
            return self._client.chat.completions.create(
                model=self.settings.llm_model,
                **kwargs,
            )
        except AuthenticationError as exc:
            raise LLMAuthenticationError("LLM provider rejected its credentials") from exc
        except RateLimitError as exc:
            raise LLMRateLimitError("LLM provider rate limit reached") from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError("LLM provider request timed out") from exc
        except APIConnectionError as exc:
            raise LLMProviderError("Could not connect to the LLM provider") from exc
        except APIStatusError as exc:
            raise LLMProviderError(
                f"LLM provider returned HTTP {exc.status_code}"
            ) from exc

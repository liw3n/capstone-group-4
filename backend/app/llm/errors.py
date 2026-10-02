class LLMError(RuntimeError):
    """Base class for errors surfaced by the configured LLM provider."""


class LLMConfigurationError(LLMError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMProviderError(LLMError):
    pass


class LLMToolLoopError(LLMError):
    pass

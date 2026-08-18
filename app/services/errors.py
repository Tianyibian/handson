class LLMConfigurationError(RuntimeError):
    """Raised when the selected LLM provider cannot be configured."""


class ConversationNotFoundError(LookupError):
    """Raised when a conversation does not exist or belongs to another user."""

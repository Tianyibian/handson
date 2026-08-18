from __future__ import annotations

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings
from app.services.base import LLMService, ServiceType
from app.services.errors import LLMConfigurationError
from app.services.ollama_service import OllamaChatService
from app.services.openai_service import OpenAIResponsesService


class LLMServiceFactory:
    """Create chat/reason/recommendation services from environment configuration."""

    _INSTRUCTIONS = {
        ServiceType.CHAT: None,
        ServiceType.REASON: (
            "Reason carefully before answering. Return a clear final answer and a concise, "
            "user-facing explanation of the important steps. Do not claim to expose hidden "
            "chain-of-thought."
        ),
        ServiceType.RECOMMENDATION: (
            "Give practical recommendations. State the criteria, tradeoffs, and any important "
            "uncertainty behind the recommendation."
        ),
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def resolve_provider(self) -> str:
        """Resolve auto at service-creation time without runtime error fallback."""
        if self.settings.llm_provider != "auto":
            return self.settings.llm_provider

        if self.settings.openai_api_key is None:
            return "ollama"
        key = self.settings.openai_api_key.get_secret_value().strip()
        placeholder_values = {
            "",
            "your_openai_api_key_here",
            "replace_with_your_own_secret_key",
        }
        return "ollama" if key in placeholder_values else "openai"

    def create(self, service_type: ServiceType) -> LLMService:
        provider = self.resolve_provider()
        if provider == "openai":
            return self._create_openai(service_type)
        if provider == "ollama":
            return self._create_ollama(service_type)
        raise LLMConfigurationError(f"Unsupported LLM provider: {provider}")

    def _create_openai(self, service_type: ServiceType) -> LLMService:
        if self.settings.openai_api_key is None:
            raise LLMConfigurationError(
                "OPENAI_API_KEY is missing. Copy .env.example to .env and add your own key."
            )

        model_by_type = {
            ServiceType.CHAT: self.settings.openai_chat_model,
            ServiceType.REASON: self.settings.openai_reason_model,
            ServiceType.RECOMMENDATION: self.settings.openai_recommendation_model,
        }
        effort = (
            "none"
            if service_type is ServiceType.CHAT
            else self.settings.openai_reasoning_effort
        )
        client = AsyncOpenAI(
            api_key=self.settings.openai_api_key.get_secret_value(),
            base_url=self.settings.openai_base_url,
            timeout=self.settings.openai_timeout_seconds,
        )
        return OpenAIResponsesService(
            client=client,
            model=model_by_type[service_type],
            service_type=service_type,
            reasoning_effort=effort,
            system_instruction=self._INSTRUCTIONS[service_type],
        )

    def _create_ollama(self, service_type: ServiceType) -> LLMService:
        model_by_type = {
            ServiceType.CHAT: self.settings.ollama_chat_model,
            ServiceType.REASON: self.settings.ollama_reason_model,
            ServiceType.RECOMMENDATION: self.settings.ollama_recommendation_model,
        }
        return OllamaChatService(
            base_url=self.settings.ollama_base_url,
            model=model_by_type[service_type],
            service_type=service_type,
            # With Qwen 3, think=True keeps reasoning in message.thinking so the
            # adapter can omit it and stream only message.content.
            think=(
                self.settings.ollama_chat_think
                if service_type is ServiceType.CHAT
                else True
            ),
            keep_alive=self.settings.ollama_keep_alive,
            timeout_seconds=self.settings.ollama_timeout_seconds,
            system_instruction=self._INSTRUCTIONS[service_type],
        )

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LLM API Integration"
    llm_provider: Literal["auto", "openai", "ollama"] = "auto"

    openai_api_key: Optional[SecretStr] = None
    openai_base_url: Optional[str] = None
    openai_chat_model: str = "gpt-5.6-luna"
    openai_reason_model: str = "gpt-5.6-terra"
    openai_recommendation_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: Literal[
        "none", "low", "medium", "high", "xhigh", "max"
    ] = "medium"
    openai_timeout_seconds: float = 60.0

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen3:4b"
    ollama_reason_model: str = "qwen3:4b"
    ollama_recommendation_model: str = "qwen3:4b"
    ollama_chat_think: bool = True
    ollama_keep_alive: str = "5m"
    ollama_timeout_seconds: float = 300.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from enum import Enum

from app.models.schemas import Message


class ServiceType(str, Enum):
    CHAT = "chat"
    REASON = "reason"
    RECOMMENDATION = "recommendation"


class LLMService(ABC):
    def __init__(self, *, model: str, service_type: ServiceType, provider: str) -> None:
        self.model = model
        self.service_type = service_type
        self.provider = provider

    @abstractmethod
    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """Yield final-answer text deltas from an LLM provider."""
        if False:  # pragma: no cover - keeps this an async generator contract.
            yield ""

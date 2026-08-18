from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from openai import AsyncOpenAI

from app.models.schemas import Message
from app.services.base import LLMService, ServiceType


class OpenAIResponsesService(LLMService):
    """OpenAI Responses API adapter used by each logical service type."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        service_type: ServiceType,
        reasoning_effort: str,
        system_instruction: str | None = None,
    ) -> None:
        super().__init__(model=model, service_type=service_type, provider="openai")
        self._client = client
        self._reasoning_effort = reasoning_effort
        self._system_instruction = system_instruction

    def _input(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if self._system_instruction:
            result.append({"role": "developer", "content": self._system_instruction})
        result.extend(message.model_dump() for message in messages)
        return result

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        stream = await self._client.responses.create(
            model=self.model,
            input=self._input(messages),
            reasoning={"effort": self._reasoning_effort},
            stream=True,
        )

        async for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta

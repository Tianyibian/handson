from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
import json
from typing import Any

import httpx

from app.models.schemas import Message
from app.services.base import LLMService, ServiceType


class OllamaChatService(LLMService):
    """Native Ollama /api/chat adapter with NDJSON streaming."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        service_type: ServiceType,
        think: bool,
        keep_alive: str,
        timeout_seconds: float,
        system_instruction: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model=model, service_type=service_type, provider="ollama")
        self._endpoint = f"{base_url.rstrip('/')}/api/chat"
        self._think = think
        self._keep_alive = keep_alive
        self._timeout = httpx.Timeout(timeout_seconds)
        self._system_instruction = system_instruction
        self._client = client

    def _messages(self, messages: Sequence[Message]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if self._system_instruction:
            result.append({"role": "system", "content": self._system_instruction})
        for message in messages:
            # Ollama uses system rather than the OpenAI developer role.
            role = "system" if message.role == "developer" else message.role
            result.append({"role": role, "content": message.content})
        return result

    async def _stream_with_client(
        self,
        client: httpx.AsyncClient,
        messages: Sequence[Message],
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(messages),
            "stream": True,
            "think": self._think,
            "keep_alive": self._keep_alive,
        }
        async with client.stream("POST", self._endpoint, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if error := chunk.get("error"):
                    raise RuntimeError(f"Ollama request failed: {error}")
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        if self._client is not None:
            async for delta in self._stream_with_client(self._client, messages):
                yield delta
            return

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async for delta in self._stream_with_client(client, messages):
                yield delta

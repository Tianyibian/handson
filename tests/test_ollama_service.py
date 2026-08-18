from __future__ import annotations

import asyncio
import json

import httpx

from app.models.schemas import Message
from app.services.base import ServiceType
from app.services.ollama_service import OllamaChatService


def test_ollama_stream_returns_content_and_hides_thinking() -> None:
    captured_payload: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        body = (
            '{"message":{"role":"assistant","thinking":"private step"},"done":false}\n'
            '{"message":{"role":"assistant","content":"The answer"},"done":false}\n'
            '{"message":{"role":"assistant","content":" is 80."},"done":false}\n'
            '{"message":{"role":"assistant","content":""},"done":true}\n'
        )
        return httpx.Response(200, content=body)

    async def scenario() -> list[str]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaChatService(
                base_url="http://ollama.test",
                model="qwen3:4b",
                service_type=ServiceType.REASON,
                think=True,
                keep_alive="5m",
                timeout_seconds=30,
                system_instruction="Explain briefly.",
                client=client,
            )
            return [
                delta
                async for delta in service.stream(
                    [Message(role="user", content="120 / 1.5?")]
                )
            ]

    assert asyncio.run(scenario()) == ["The answer", " is 80."]
    assert captured_payload["model"] == "qwen3:4b"
    assert captured_payload["stream"] is True
    assert captured_payload["think"] is True
    assert captured_payload["messages"][0] == {
        "role": "system",
        "content": "Explain briefly.",
    }


def test_ollama_maps_developer_role_to_system() -> None:
    service = OllamaChatService(
        base_url="http://ollama.test",
        model="qwen3:4b",
        service_type=ServiceType.CHAT,
        think=False,
        keep_alive="5m",
        timeout_seconds=30,
    )

    assert service._messages([Message(role="developer", content="Be concise.")]) == [
        {"role": "system", "content": "Be concise."}
    ]

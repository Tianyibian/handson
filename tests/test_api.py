from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from fastapi.testclient import TestClient

from app.api.routes import get_llm_factory
from app.main import app
from app.models.schemas import Message
from app.services.base import LLMService, ServiceType


class FakeService(LLMService):
    def __init__(self, service_type: ServiceType) -> None:
        super().__init__(
            model=f"fake-{service_type.value}-model",
            service_type=service_type,
            provider="fake",
        )

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        yield "Hello"
        yield " from test"


class FakeFactory:
    def create(self, service_type: ServiceType) -> LLMService:
        return FakeService(service_type)


def fake_factory_dependency() -> FakeFactory:
    return FakeFactory()


app.dependency_overrides[get_llm_factory] = fake_factory_dependency
client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_streams_sse() -> None:
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"service": "chat"' in response.text
    assert 'data: {"content": "Hello"}' in response.text
    assert 'data: {"content": " from test"}' in response.text
    assert 'data: "[DONE]"' in response.text


def test_reason_uses_reason_service() -> None:
    response = client.post(
        "/api/reason",
        json={"messages": [{"role": "user", "content": "Why is the sky blue?"}]},
    )

    assert response.status_code == 200
    assert '"service": "reason"' in response.text
    assert '"model": "fake-reason-model"' in response.text


def test_empty_messages_is_rejected() -> None:
    response = client.post("/api/chat", json={"messages": []})
    assert response.status_code == 422


def test_blank_message_is_rejected() -> None:
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "   "}]},
    )
    assert response.status_code == 422

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
import json

from fastapi.testclient import TestClient
import pytest

from app.api.conversation_routes import get_conversation_service
from app.api.routes import get_llm_factory
from app.db.session import build_database, create_tables
from app.main import app
from app.models.schemas import Message
from app.services.base import LLMService, ServiceType
from app.services.conversation_service import ConversationService


class FakeService(LLMService):
    def __init__(
        self,
        service_type: ServiceType,
        calls: list[list[Message]],
    ) -> None:
        super().__init__(
            model=f"fake-{service_type.value}-model",
            service_type=service_type,
            provider="fake",
        )
        self._calls = calls

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        self._calls.append([message.model_copy() for message in messages])
        yield "Hello"
        yield " from test"


class FakeFactory:
    def __init__(self) -> None:
        self.calls: list[list[Message]] = []

    def create(self, service_type: ServiceType) -> LLMService:
        return FakeService(service_type, self.calls)


class FailingService(LLMService):
    def __init__(self) -> None:
        super().__init__(
            model="failing-model",
            service_type=ServiceType.CHAT,
            provider="fake",
        )

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        yield "partial"
        raise RuntimeError("simulated provider failure")


class FailingFactory:
    def create(self, service_type: ServiceType) -> LLMService:
        return FailingService()


@pytest.fixture
def api_client(tmp_path):
    engine, session_factory = build_database(
        f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    )
    asyncio.run(create_tables(engine))

    fake_factory = FakeFactory()
    conversation_service = ConversationService(session_factory)
    app.dependency_overrides[get_llm_factory] = lambda: fake_factory
    app.dependency_overrides[get_conversation_service] = lambda: conversation_service
    client = TestClient(app)

    yield client, fake_factory

    client.close()
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _sse_payload(response_text: str, event_name: str) -> dict:
    for block in response_text.split("\n\n"):
        lines = block.splitlines()
        if f"event: {event_name}" not in lines:
            continue
        data_line = next(line for line in lines if line.startswith("data: "))
        return json.loads(data_line.removeprefix("data: "))
    raise AssertionError(f"SSE event {event_name!r} was not found")


def test_health(api_client) -> None:
    client, _ = api_client
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_creates_conversation_and_streams_sse(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"service": "chat"' in response.text
    assert 'data: {"content": "Hello"}' in response.text
    assert 'data: {"content": " from test"}' in response.text
    assert 'data: "[DONE]"' in response.text

    metadata = _sse_payload(response.text, "metadata")
    conversation_id = metadata["conversation_id"]
    messages = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "user-1"},
    )
    assert messages.status_code == 200
    assert [(item["role"], item["content"]) for item in messages.json()] == [
        ("user", "Hi"),
        ("assistant", "Hello from test"),
    ]


def test_second_chat_turn_receives_database_history(api_client) -> None:
    client, factory = api_client
    first = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "messages": [
                {"role": "user", "content": "Remember that I prefer FastAPI."}
            ],
        },
    )
    conversation_id = _sse_payload(first.text, "metadata")["conversation_id"]

    second = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "conversation_id": conversation_id,
            "messages": [
                {"role": "user", "content": "Which framework do I prefer?"}
            ],
        },
    )

    assert second.status_code == 200
    assert len(factory.calls) == 2
    assert [(message.role, message.content) for message in factory.calls[1]] == [
        ("user", "Remember that I prefer FastAPI."),
        ("assistant", "Hello from test"),
        ("user", "Which framework do I prefer?"),
    ]

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "user-1"},
    )
    assert [item["role"] for item in messages.json()] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_conversation_endpoints_enforce_user_ownership(api_client) -> None:
    client, _ = api_client
    created = client.post(
        "/api/conversations",
        json={"user_id": "owner", "title": "Architecture"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    conversations = client.get("/api/users/owner/conversations")
    assert conversations.status_code == 200
    assert conversations.json()[0]["id"] == conversation_id

    forbidden = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "another-user"},
    )
    assert forbidden.status_code == 404

    chat = client.post(
        "/api/chat",
        json={
            "user_id": "another-user",
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "Unauthorized turn"}],
        },
    )
    assert chat.status_code == 404


def test_failed_stream_does_not_persist_partial_turn(api_client) -> None:
    client, _ = api_client
    created = client.post(
        "/api/conversations",
        json={"user_id": "user-1", "title": "Failure test"},
    )
    conversation_id = created.json()["id"]
    app.dependency_overrides[get_llm_factory] = lambda: FailingFactory()

    response = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "Do not save this partially"}],
        },
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert 'data: "[DONE]"' not in response.text
    messages = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "user-1"},
    )
    assert messages.json() == []


def test_failed_first_stream_removes_auto_created_empty_conversation(api_client) -> None:
    client, _ = api_client
    app.dependency_overrides[get_llm_factory] = lambda: FailingFactory()

    response = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "messages": [{"role": "user", "content": "This call will fail"}],
        },
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    conversation_id = _sse_payload(response.text, "metadata")["conversation_id"]
    conversations = client.get("/api/users/user-1/conversations")
    assert conversations.status_code == 200
    assert all(item["id"] != conversation_id for item in conversations.json())

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "user-1"},
    )
    assert messages.status_code == 404


def test_update_and_delete_conversation_enforce_ownership(api_client) -> None:
    client, _ = api_client
    created = client.post(
        "/api/conversations",
        json={"user_id": "owner", "title": "Original title"},
    )
    conversation_id = created.json()["id"]

    turn = client.post(
        "/api/chat",
        json={
            "user_id": "owner",
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "Persist this turn"}],
        },
    )
    assert 'data: "[DONE]"' in turn.text

    unauthorized_update = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"user_id": "another-user", "title": "Stolen title"},
    )
    assert unauthorized_update.status_code == 404

    updated = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"user_id": "owner", "title": "  Updated title  "},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated title"

    unauthorized_delete = client.delete(
        f"/api/conversations/{conversation_id}",
        params={"user_id": "another-user"},
    )
    assert unauthorized_delete.status_code == 404

    messages_before_delete = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "owner"},
    )
    assert len(messages_before_delete.json()) == 2

    deleted = client.delete(
        f"/api/conversations/{conversation_id}",
        params={"user_id": "owner"},
    )
    assert deleted.status_code == 204
    assert deleted.content == b""

    messages_after_delete = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"user_id": "owner"},
    )
    assert messages_after_delete.status_code == 404


def test_update_conversation_rejects_blank_title(api_client) -> None:
    client, _ = api_client
    created = client.post(
        "/api/conversations",
        json={"user_id": "owner", "title": "Original title"},
    )

    response = client.patch(
        f"/api/conversations/{created.json()['id']}",
        json={"user_id": "owner", "title": "   "},
    )

    assert response.status_code == 422


def test_reason_uses_reason_service(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/reason",
        json={"messages": [{"role": "user", "content": "Why is the sky blue?"}]},
    )

    assert response.status_code == 200
    assert '"service": "reason"' in response.text
    assert '"model": "fake-reason-model"' in response.text


def test_chat_requires_user_id(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert response.status_code == 422


def test_empty_messages_is_rejected(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/chat",
        json={"user_id": "user-1", "messages": []},
    )
    assert response.status_code == 422


def test_blank_message_is_rejected(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "messages": [{"role": "user", "content": "   "}],
        },
    )
    assert response.status_code == 422


def test_chat_turn_must_end_with_user_message(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/chat",
        json={
            "user_id": "user-1",
            "messages": [{"role": "assistant", "content": "Not a new user turn"}],
        },
    )
    assert response.status_code == 422

from __future__ import annotations

import asyncio

import pytest

from app.db.session import build_database, create_tables
from app.services.conversation_service import ConversationService
from app.services.errors import ConversationNotFoundError


def test_conversation_service_crud_and_atomic_turn(tmp_path) -> None:
    async def scenario() -> None:
        engine, session_factory = build_database(
            f"sqlite+aiosqlite:///{tmp_path / 'service.db'}"
        )
        await create_tables(engine)
        service = ConversationService(session_factory)

        first = await service.create_conversation("user-1", "First conversation")
        second = await service.create_conversation("user-1", "Second conversation")

        await service.save_message("user-1", first.id, "user", "First question")
        await service.save_message("user-1", first.id, "assistant", "First answer")
        await service.save_turn(
            "user-1",
            first.id,
            "Follow-up question",
            "Follow-up answer",
        )

        messages = await service.get_conversation_messages("user-1", first.id)
        assert [(message.role, message.content) for message in messages] == [
            ("user", "First question"),
            ("assistant", "First answer"),
            ("user", "Follow-up question"),
            ("assistant", "Follow-up answer"),
        ]

        conversations = await service.get_user_conversations("user-1")
        assert {conversation.id for conversation in conversations} == {
            first.id,
            second.id,
        }

        with pytest.raises(ConversationNotFoundError):
            await service.get_conversation_messages("another-user", first.id)

        await engine.dispose()

    asyncio.run(scenario())

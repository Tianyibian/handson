from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.db.models import ConversationMessage
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

        updated = await service.update_conversation_title(
            "user-1", first.id, "  Updated title  "
        )
        assert updated.title == "Updated title"

        with pytest.raises(ConversationNotFoundError):
            await service.update_conversation_title(
                "another-user", first.id, "Unauthorized title"
            )

        with pytest.raises(ConversationNotFoundError):
            await service.delete_conversation("another-user", first.id)

        assert await service.delete_conversation_if_empty("user-1", first.id) is False
        await service.delete_conversation("user-1", first.id)
        with pytest.raises(ConversationNotFoundError):
            await service.get_conversation_messages("user-1", first.id)

        async with session_factory() as session:
            remaining_messages = await session.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.conversation_id == first.id)
            )
        assert remaining_messages == 0

        empty = await service.create_conversation("user-1", "Empty conversation")
        assert await service.delete_conversation_if_empty("user-1", empty.id) is True
        assert await service.delete_conversation_if_empty("user-1", second.id) is True

        with pytest.raises(ConversationNotFoundError):
            await service.get_conversation_messages("another-user", first.id)

        await engine.dispose()

    asyncio.run(scenario())

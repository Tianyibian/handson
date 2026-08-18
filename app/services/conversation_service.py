from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, ConversationMessage
from app.services.errors import ConversationNotFoundError

StoredRole = Literal["user", "assistant"]


class ConversationService:
    """Own conversation persistence and user-ownership checks."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _owned_conversation_query(
        user_id: str,
        conversation_id: str,
    ) -> Select[tuple[Conversation]]:
        return select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )

    async def _require_owned_conversation(
        self,
        session: AsyncSession,
        user_id: str,
        conversation_id: str,
    ) -> Conversation:
        conversation = await session.scalar(
            self._owned_conversation_query(user_id, conversation_id)
        )
        if conversation is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id!r} was not found for this user."
            )
        return conversation

    async def create_conversation(
        self,
        user_id: str,
        title: str | None = None,
    ) -> Conversation:
        """Create and return a conversation owned by user_id."""
        conversation = Conversation(user_id=user_id, title=title)
        async with self._session_factory() as session:
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
        return conversation

    async def get_conversation_messages(
        self,
        user_id: str,
        conversation_id: str,
    ) -> list[ConversationMessage]:
        """Return an owned conversation's messages in insertion order."""
        async with self._session_factory() as session:
            await self._require_owned_conversation(session, user_id, conversation_id)
            result = await session.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.id)
            )
            return list(result.all())

    async def save_message(
        self,
        user_id: str,
        conversation_id: str,
        role: StoredRole,
        content: str,
    ) -> ConversationMessage:
        """Persist one message after validating conversation ownership."""
        if role not in {"user", "assistant"}:
            raise ValueError("Stored message role must be 'user' or 'assistant'.")

        async with self._session_factory() as session:
            conversation = await self._require_owned_conversation(
                session, user_id, conversation_id
            )
            message = ConversationMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
            )
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def save_turn(
        self,
        user_id: str,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """Atomically persist both messages from one completed chat turn."""
        async with self._session_factory.begin() as session:
            conversation = await self._require_owned_conversation(
                session, user_id, conversation_id
            )
            user_message = ConversationMessage(
                conversation_id=conversation_id,
                role="user",
                content=user_content,
            )
            assistant_message = ConversationMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_content,
            )
            conversation.updated_at = datetime.now(timezone.utc)
            session.add_all([user_message, assistant_message])

        return user_message, assistant_message

    async def get_user_conversations(self, user_id: str) -> Sequence[Conversation]:
        """Return a user's conversations, most recently updated first."""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            )
            return result.all()

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Message(BaseModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message content must not be blank")
        return value


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)


class ConversationChatRequest(ChatRequest):
    user_id: str = Field(min_length=1, max_length=255)
    conversation_id: Optional[UUID] = None

    @field_validator("user_id")
    @classmethod
    def user_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("user_id must not be blank")
        return value

    @field_validator("messages")
    @classmethod
    def last_message_must_be_from_user(cls, value: list[Message]) -> list[Message]:
        if value[-1].role != "user":
            raise ValueError("the final message in a chat turn must have role 'user'")
        return value

    @property
    def current_user_message(self) -> Message:
        return self.messages[-1]


class ConversationCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=200)

    @field_validator("user_id")
    @classmethod
    def user_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("user_id must not be blank")
        return value

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ConversationUpdateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=200)

    @field_validator("user_id", "title")
    @classmethod
    def fields_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

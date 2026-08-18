from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.session import async_session_factory
from app.models.schemas import (
    ConversationCreateRequest,
    ConversationMessageResponse,
    ConversationResponse,
)
from app.services.conversation_service import ConversationService
from app.services.errors import ConversationNotFoundError

router = APIRouter(prefix="/api", tags=["conversations"])


def get_conversation_service() -> ConversationService:
    return ConversationService(async_session_factory)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation",
)
async def create_conversation(
    request: ConversationCreateRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    conversation = await service.create_conversation(request.user_id, request.title)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/users/{user_id}/conversations",
    response_model=list[ConversationResponse],
    summary="List a user's conversations",
)
async def get_user_conversations(
    user_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationResponse]:
    conversations = await service.get_user_conversations(user_id)
    return [ConversationResponse.model_validate(item) for item in conversations]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessageResponse],
    summary="List messages in a conversation",
)
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Query(min_length=1, max_length=255),
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationMessageResponse]:
    try:
        messages = await service.get_conversation_messages(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [ConversationMessageResponse.model_validate(item) for item in messages]

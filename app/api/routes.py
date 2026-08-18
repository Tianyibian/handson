from __future__ import annotations

from collections.abc import AsyncIterator
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.conversation_routes import get_conversation_service
from app.models.schemas import ChatRequest, ConversationChatRequest, Message
from app.services.base import LLMService, ServiceType
from app.services.conversation_service import ConversationService
from app.services.errors import ConversationNotFoundError, LLMConfigurationError
from app.services.factory import LLMServiceFactory
from app.services.streaming import encode_sse

router = APIRouter(prefix="/api", tags=["llm"])
logger = logging.getLogger(__name__)


def get_llm_factory() -> LLMServiceFactory:
    return LLMServiceFactory()


async def _stream(service: LLMService, request: ChatRequest) -> AsyncIterator[str]:
    yield encode_sse(
        "metadata",
        {
            "provider": service.provider,
            "model": service.model,
            "service": service.service_type.value,
        },
    )
    try:
        async for delta in service.stream(request.messages):
            yield encode_sse("delta", {"content": delta})
        yield encode_sse("done", "[DONE]")
    except Exception as exc:  # The HTTP headers have already been sent for a stream.
        logger.exception("LLM stream failed")
        yield encode_sse(
            "error",
            {
                "type": type(exc).__name__,
                "message": "LLM request failed. Check the server log and configuration.",
            },
        )


async def _stream_conversation(
    service: LLMService,
    messages: list[Message],
    request: ConversationChatRequest,
    conversation_id: str,
    conversation_service: ConversationService,
) -> AsyncIterator[str]:
    yield encode_sse(
        "metadata",
        {
            "provider": service.provider,
            "model": service.model,
            "service": service.service_type.value,
            "conversation_id": conversation_id,
        },
    )
    assistant_chunks: list[str] = []
    try:
        async for delta in service.stream(messages):
            assistant_chunks.append(delta)
            yield encode_sse("delta", {"content": delta})

        assistant_content = "".join(assistant_chunks)
        if not assistant_content.strip():
            raise RuntimeError("The LLM returned an empty response.")

        await conversation_service.save_turn(
            request.user_id,
            conversation_id,
            request.current_user_message.content,
            assistant_content,
        )
        yield encode_sse("done", "[DONE]")
    except Exception as exc:
        logger.exception("Stateful LLM stream failed")
        yield encode_sse(
            "error",
            {
                "type": type(exc).__name__,
                "message": "LLM request or conversation persistence failed.",
            },
        )


def _create_streaming_response(
    request: ChatRequest,
    factory: LLMServiceFactory,
    service_type: ServiceType,
) -> StreamingResponse:
    try:
        service = factory.create(service_type)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return StreamingResponse(
        _stream(service, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/chat",
    response_class=StreamingResponse,
    summary="Stream a conversational response",
)
async def chat(
    request: ConversationChatRequest,
    factory: LLMServiceFactory = Depends(get_llm_factory),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> StreamingResponse:
    try:
        service = factory.create(ServiceType.CHAT)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if request.conversation_id is None:
        title = " ".join(request.current_user_message.content.split())[:80]
        conversation = await conversation_service.create_conversation(
            request.user_id,
            title or None,
        )
        conversation_id = conversation.id
        history: list[Message] = []
    else:
        conversation_id = str(request.conversation_id)
        try:
            stored_messages = await conversation_service.get_conversation_messages(
                request.user_id,
                conversation_id,
            )
        except ConversationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        history = [
            Message(role=message.role, content=message.content)
            for message in stored_messages
        ]

    llm_messages = [*history, *request.messages]
    return StreamingResponse(
        _stream_conversation(
            service,
            llm_messages,
            request,
            conversation_id,
            conversation_service,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/reason",
    response_class=StreamingResponse,
    summary="Stream a reasoning result",
)
async def reason(
    request: ChatRequest,
    factory: LLMServiceFactory = Depends(get_llm_factory),
) -> StreamingResponse:
    return _create_streaming_response(request, factory, ServiceType.REASON)

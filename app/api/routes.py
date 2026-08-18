from __future__ import annotations

from collections.abc import AsyncIterator
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.services.base import LLMService, ServiceType
from app.services.errors import LLMConfigurationError
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
    request: ChatRequest,
    factory: LLMServiceFactory = Depends(get_llm_factory),
) -> StreamingResponse:
    return _create_streaming_response(request, factory, ServiceType.CHAT)


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

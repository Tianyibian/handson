from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.services.factory import LLMServiceFactory

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Streaming chat and reasoning endpoints backed by an LLM service factory.",
)
app.include_router(router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "configured_provider": settings.llm_provider,
        "provider": LLMServiceFactory(settings).resolve_provider(),
    }

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.base import Base


def build_database(
    database_url: str,
    *,
    echo: bool = False,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build an async engine and reusable session factory."""
    engine = create_async_engine(database_url, echo=echo)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


settings = get_settings()
engine, async_session_factory = build_database(
    settings.database_url,
    echo=settings.database_echo,
)


async def create_tables(database_engine: AsyncEngine = engine) -> None:
    """Create missing tables directly for isolated test databases."""
    # Import models here so their table metadata is registered before create_all.
    from app.db import models  # noqa: F401

    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

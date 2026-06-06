from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def create_database_engine(database_url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(database_url or settings.database_url, pool_pre_ping=True)


engine = create_database_engine()
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def check_database_connection(database_url: str | None = None) -> None:
    readiness_engine = create_database_engine(database_url)
    try:
        async with readiness_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await readiness_engine.dispose()

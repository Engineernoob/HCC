"""
Async SQLAlchemy engine + session factory.
Uses asyncpg driver for PostgreSQL.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import create_engine, text

from hirectl.config import settings
from hirectl.db.models import Base


# ── Async engine (used everywhere in the app) ─────────────────────
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Sync engine (used only for Alembic migrations) ────────────────
sync_engine = create_engine(
    settings.database_sync_url,
    echo=False,
    pool_pre_ping=True,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injectable async session context manager."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables. Used in development; use Alembic in production."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_connection() -> bool:
    """Verify the database is reachable."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

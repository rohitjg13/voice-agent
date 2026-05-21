"""Asyncpg connection pool — created once at app startup."""

import asyncpg
import structlog

from orchestrator.config import settings

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    # Strip SQLAlchemy dialect prefix if someone copies from DATABASE_URL
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def init_pool() -> None:
    global _pool
    if not settings.database_url:
        logger.warning("db_pool_skipped", reason="DATABASE_URL not set")
        return
    _pool = await asyncpg.create_pool(_dsn(), min_size=1, max_size=5, ssl="require")
    # Register pgvector codec on every connection
    from pgvector.asyncpg import register_vector

    async with _pool.acquire() as conn:
        await register_vector(conn)
    logger.info("db_pool_ready")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    return _pool


def set_pool(pool: asyncpg.Pool | None) -> None:
    """Test helper — inject a pool (or None) without touching the DB."""
    global _pool
    _pool = pool

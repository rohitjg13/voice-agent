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
    """Create the pool, degrading to pool-less mode if the DB is unreachable.

    Everything that uses the pool (RAG retrieval, appointment persistence)
    already handles a missing pool — a DB outage should cost us knowledge
    grounding, not the ability to answer phone calls.
    """
    global _pool
    if not settings.database_url:
        logger.warning("db_pool_skipped", reason="DATABASE_URL not set")
        return
    try:
        dsn = _dsn()
        # Respect an explicit sslmode in the DSN (self-hosted Postgres often has
        # no TLS); default to require for hosted Supabase.
        ssl_arg = None if "sslmode=" in dsn else "require"
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, ssl=ssl_arg)
        # Register pgvector codec on every connection
        from pgvector.asyncpg import register_vector

        async with _pool.acquire() as conn:
            await register_vector(conn)
    except Exception as exc:
        logger.error("db_pool_failed", error=str(exc))
        _pool = None
        return
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


async def connect_direct() -> asyncpg.Connection:
    """One-off direct connection for CLI scripts — honors ?sslmode= in the DSN."""
    dsn = _dsn()
    return await asyncpg.connect(dsn, ssl=None if "sslmode=" in dsn else "require")


def require_pool() -> asyncpg.Pool:
    """Pool or 503 — the dashboard API does not degrade gracefully like the voice path."""
    if _pool is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Database unavailable")
    return _pool

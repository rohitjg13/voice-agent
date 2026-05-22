"""
Redis-backed call state store.
Falls back to an in-process dict when Redis is not configured (dev / CI).
"""

import structlog

from orchestrator.config import settings
from orchestrator.models.call_state import CallState, ConversationState

logger = structlog.get_logger()

_TTL_SECONDS = 4 * 60 * 60  # 4 hours — max expected call duration

# In-memory fallback used when UPSTASH_REDIS_REST_URL is unset
_mem: dict[str, str] = {}


def _redis_configured() -> bool:
    return bool(settings.upstash_redis_rest_url and settings.upstash_redis_rest_token)


async def _redis_get(key: str) -> str | None:
    from upstash_redis.asyncio import Redis

    client = Redis(
        url=settings.upstash_redis_rest_url,
        token=settings.upstash_redis_rest_token,
    )
    return await client.get(key)


async def _redis_set(key: str, value: str, ttl: int) -> None:
    from upstash_redis.asyncio import Redis

    client = Redis(
        url=settings.upstash_redis_rest_url,
        token=settings.upstash_redis_rest_token,
    )
    await client.set(key, value, ex=ttl)


async def get_call_state(call_id: str) -> CallState | None:
    key = f"call:{call_id}"
    if _redis_configured():
        raw = await _redis_get(key)
    else:
        raw = _mem.get(key)

    if raw is None:
        return None
    return CallState.model_validate_json(raw)


async def save_call_state(call_id: str, state: CallState) -> None:
    key = f"call:{call_id}"
    payload = state.model_dump_json()
    if _redis_configured():
        await _redis_set(key, payload, _TTL_SECONDS)
    else:
        _mem[key] = payload


async def get_or_create_call_state(call_id: str, pack_name: str) -> CallState:
    state = await get_call_state(call_id)
    if state is None:
        state = CallState(
            call_id=call_id,
            pack_name=pack_name,
            stage=ConversationState.OPENER,
        )
        logger.info("new_call", call_id=call_id, pack=pack_name)
    return state


def clear_mem_store() -> None:
    """Test helper — clears the in-memory fallback store."""
    _mem.clear()

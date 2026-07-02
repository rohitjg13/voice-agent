"""
Redis-backed call state store.
Falls back to an in-process dict when Redis is not configured (dev / CI).
"""

from typing import Any

import structlog

from orchestrator.config import settings
from orchestrator.models.call_state import CallState, ConversationState

logger = structlog.get_logger()

_TTL_SECONDS = 4 * 60 * 60  # 4 hours — max expected call duration

# In-memory fallback used when UPSTASH_REDIS_REST_URL is unset.
# Bounded so an unauthenticated dev deployment can't be ballooned by
# random call_ids; entries have no TTL here, so oldest-first eviction.
_mem: dict[str, str] = {}
_MEM_MAX_ENTRIES = 1000

_redis_client: Any = None


def _redis_configured() -> bool:
    return bool(settings.upstash_redis_rest_url and settings.upstash_redis_rest_token)


def _get_redis() -> Any:
    """One client per process — each instance owns an HTTP session, and
    constructing one per operation would add a connection setup to every turn."""
    global _redis_client
    if _redis_client is None:
        from upstash_redis.asyncio import Redis

        _redis_client = Redis(
            url=settings.upstash_redis_rest_url,
            token=settings.upstash_redis_rest_token,
        )
    return _redis_client


async def _redis_get(key: str) -> str | None:
    result = await _get_redis().get(key)
    return result if isinstance(result, str) else None


async def _redis_set(key: str, value: str, ttl: int) -> None:
    await _get_redis().set(key, value, ex=ttl)


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
        if key not in _mem and len(_mem) >= _MEM_MAX_ENTRIES:
            _mem.pop(next(iter(_mem)))  # evict oldest (insertion order)
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
    """Test helper — clears the in-memory fallback store and cached client."""
    global _redis_client
    _mem.clear()
    _redis_client = None

"""Map an inbound Vapi call to a tenant agent config.

Chain: call.assistantId → agents lookup → call.metadata.agent_id → YAML
ACTIVE_PACK fallback (simulator / CI / legacy deployment / DB down). The
voice path must keep answering when the DB is unavailable, so every lookup
failure degrades to the fallback instead of raising.
"""

import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel

from orchestrator.config import settings
from orchestrator.db import get_pool
from orchestrator.services import agent_config_store
from orchestrator.services.agent_config_store import AgentCallInfo
from packs._schema.pack import IndustryPack
from packs.pack_loader import load_pack

logger = structlog.get_logger()

_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, AgentCallInfo]] = {}


class ResolvedAgent(BaseModel):
    pack: IndustryPack
    org_id: UUID | None = None
    agent_id: UUID | None = None


def clear_cache() -> None:
    _cache.clear()


def _fallback() -> ResolvedAgent:
    return ResolvedAgent(pack=load_pack(settings.active_pack))


async def _cached_lookup(
    key: str, fetch: Callable[[], Awaitable[AgentCallInfo | None]]
) -> AgentCallInfo | None:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    info = await fetch()
    if info is not None:
        _cache[key] = (time.monotonic(), info)
    return info


async def resolve_agent(call: dict[str, Any] | None) -> ResolvedAgent:
    call = call if isinstance(call, dict) else {}
    if get_pool() is None:
        return _fallback()

    try:
        assistant_id = call.get("assistantId")
        if isinstance(assistant_id, str) and assistant_id:
            info = await _cached_lookup(
                f"assistant:{assistant_id}",
                lambda: agent_config_store.get_agent_by_assistant_id(assistant_id),
            )
            if info:
                return ResolvedAgent(
                    pack=info.pack, org_id=info.org_id, agent_id=info.agent_id
                )
            logger.warning("unknown_assistant_id", assistant_id=assistant_id)

        metadata = call.get("metadata")
        raw_agent_id = metadata.get("agent_id") if isinstance(metadata, dict) else None
        if raw_agent_id:
            agent_id = UUID(str(raw_agent_id))
            info = await _cached_lookup(
                f"agent:{agent_id}",
                lambda: agent_config_store.get_agent_call_info(agent_id),
            )
            if info:
                return ResolvedAgent(
                    pack=info.pack, org_id=info.org_id, agent_id=info.agent_id
                )
            logger.warning("unknown_agent_id", agent_id=str(agent_id))
    except Exception as exc:
        logger.warning("tenant_resolution_failed", error=str(exc))

    return _fallback()

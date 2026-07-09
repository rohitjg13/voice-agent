"""Per-tenant agent configs stored as JSONB, validated through IndustryPack
in both directions — the pydantic schema stays the single validation layer."""

import json
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel

from orchestrator.db import require_pool
from packs._schema.pack import IndustryPack

logger = structlog.get_logger()


class AgentCallInfo(BaseModel):
    """What the live call path needs: identity + validated pack config."""

    agent_id: UUID
    org_id: UUID
    pack: IndustryPack


def _parse_config(raw: Any) -> IndustryPack:
    data = json.loads(raw) if isinstance(raw, str) else raw
    return IndustryPack.model_validate(data)


async def list_templates() -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        "SELECT name, version, config FROM pack_templates WHERE org_id IS NULL ORDER BY name"
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        cfg = json.loads(r["config"]) if isinstance(r["config"], str) else r["config"]
        out.append(
            {
                "name": r["name"],
                "version": r["version"],
                "industry": cfg.get("industry", ""),
                "agent_name": cfg.get("agent", {}).get("name", ""),
                "product_name": cfg.get("product", {}).get("name", ""),
            }
        )
    return out


async def get_template_config(name: str, org_id: UUID | None = None) -> IndustryPack | None:
    pool = require_pool()
    if org_id:
        row = await pool.fetchrow(
            """SELECT config FROM pack_templates
               WHERE name = $1 AND (org_id IS NULL OR org_id = $2)
               ORDER BY org_id NULLS FIRST LIMIT 1""",
            name, org_id,
        )
    else:
        row = await pool.fetchrow(
            "SELECT config FROM pack_templates WHERE name = $1 AND org_id IS NULL",
            name,
        )
    return _parse_config(row["config"]) if row else None


async def create_agent(
    org_id: UUID, name: str, template_name: str
) -> dict[str, Any] | None:
    """Copy-on-create from a template. None = unknown template."""
    template = await get_template_config(template_name, org_id)
    if template is None:
        return None
    pool = require_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO agents (org_id, name, template_name, config)
        VALUES ($1, $2, $3, $4)
        RETURNING id, status
        """,
        org_id,
        name,
        template_name,
        json.dumps(template.model_dump()),
    )
    logger.info("agent_created", org_id=str(org_id), agent_id=str(row["id"]))
    return {
        "id": str(row["id"]),
        "name": name,
        "template_name": template_name,
        "status": row["status"],
    }


async def count_agents(org_id: UUID) -> int:
    pool = require_pool()
    count: int = await pool.fetchval(
        "SELECT COUNT(*) FROM agents WHERE org_id = $1 AND status != 'archived'",
        org_id,
    )
    return count


async def list_agents(org_id: UUID) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        """
        SELECT id, name, template_name, status, vapi_assistant_id, updated_at
        FROM agents WHERE org_id = $1 ORDER BY created_at
        """,
        org_id,
    )
    return [dict(r) for r in rows]


async def get_agent(org_id: UUID, agent_id: UUID) -> dict[str, Any] | None:
    pool = require_pool()
    row = await pool.fetchrow(
        """
        SELECT id, name, template_name, status, vapi_assistant_id,
               created_at, updated_at, config
        FROM agents WHERE org_id = $1 AND id = $2
        """,
        org_id,
        agent_id,
    )
    if row is None:
        return None
    out = dict(row)
    out["config"] = _parse_config(out["config"]).model_dump()
    return out


async def update_agent_config(
    org_id: UUID, agent_id: UUID, pack: IndustryPack
) -> bool:
    pool = require_pool()
    result: str = await pool.execute(
        "UPDATE agents SET config = $3, updated_at = NOW() WHERE org_id = $1 AND id = $2",
        org_id,
        agent_id,
        json.dumps(pack.model_dump()),
    )
    return result.endswith(" 1")


async def set_vapi_assistant_id(
    org_id: UUID, agent_id: UUID, vapi_assistant_id: str
) -> bool:
    """Record the published Vapi assistant and flip the agent active."""
    pool = require_pool()
    result: str = await pool.execute(
        """
        UPDATE agents SET vapi_assistant_id = $3, status = 'active', updated_at = NOW()
        WHERE org_id = $1 AND id = $2
        """,
        org_id,
        agent_id,
        vapi_assistant_id,
    )
    return result.endswith(" 1")


# ── custom org packs CRUD ───────────────────────────────────────────────────


async def list_custom_packs(org_id: UUID) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        "SELECT name, version, config FROM pack_templates WHERE org_id = $1 ORDER BY name",
        org_id,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        cfg = json.loads(r["config"]) if isinstance(r["config"], str) else r["config"]
        out.append(
            {
                "name": r["name"],
                "version": r["version"],
                "industry": cfg.get("industry", ""),
                "agent_name": cfg.get("agent", {}).get("name", ""),
                "product_name": cfg.get("product", {}).get("name", ""),
            }
        )
    return out


async def get_custom_pack(org_id: UUID, name: str) -> IndustryPack | None:
    pool = require_pool()
    row = await pool.fetchrow(
        "SELECT config FROM pack_templates WHERE name = $1 AND org_id = $2",
        name, org_id,
    )
    return _parse_config(row["config"]) if row else None


async def create_custom_pack(org_id: UUID, pack: IndustryPack) -> bool:
    pool = require_pool()
    try:
        await pool.execute(
            """INSERT INTO pack_templates (name, version, config, org_id)
               VALUES ($1, $2, $3, $4)""",
            pack.name, pack.version, json.dumps(pack.model_dump()), org_id,
        )
        return True
    except Exception:
        return False


async def update_custom_pack(org_id: UUID, name: str, pack: IndustryPack) -> bool:
    pool = require_pool()
    result: str = await pool.execute(
        """UPDATE pack_templates
           SET version = $3, config = $4, updated_at = NOW()
           WHERE name = $1 AND org_id = $2""",
        name, org_id, pack.version, json.dumps(pack.model_dump()),
    )
    return result.endswith(" 1")


async def delete_custom_pack(org_id: UUID, name: str) -> bool:
    pool = require_pool()
    result: str = await pool.execute(
        "DELETE FROM pack_templates WHERE name = $1 AND org_id = $2",
        name, org_id,
    )
    return result.endswith(" 1")


# ── live call path lookups (used by tenant_resolver) ─────────────────────────


def _call_info(row: Any) -> AgentCallInfo:
    return AgentCallInfo(
        agent_id=row["id"], org_id=row["org_id"], pack=_parse_config(row["config"])
    )


async def get_agent_by_assistant_id(vapi_assistant_id: str) -> AgentCallInfo | None:
    pool = require_pool()
    row = await pool.fetchrow(
        "SELECT id, org_id, config FROM agents WHERE vapi_assistant_id = $1",
        vapi_assistant_id,
    )
    return _call_info(row) if row else None


async def get_agent_call_info(agent_id: UUID) -> AgentCallInfo | None:
    pool = require_pool()
    row = await pool.fetchrow(
        "SELECT id, org_id, config FROM agents WHERE id = $1", agent_id
    )
    return _call_info(row) if row else None

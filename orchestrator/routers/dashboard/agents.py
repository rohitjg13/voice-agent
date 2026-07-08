from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.services import (
    agent_config_store,
    entitlements,
    tenant_resolver,
    vapi_client,
)
from orchestrator.services.dashboard_auth import AuthCtx, OrgCtx
from packs._schema.pack import IndustryPack

router = APIRouter()


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template_name: str = Field(min_length=1, max_length=80)


@router.get("/templates")
async def list_templates(ctx: AuthCtx) -> list[dict[str, Any]]:
    return await agent_config_store.list_templates()


@router.get("/agents")
async def list_agents(ctx: OrgCtx) -> list[dict[str, Any]]:
    return await agent_config_store.list_agents(ctx.org_id)


@router.post("/agents", status_code=201)
async def create_agent(body: AgentCreate, ctx: OrgCtx) -> dict[str, Any]:
    await entitlements.check_can_create_agent(ctx.org_id)
    agent = await agent_config_store.create_agent(
        ctx.org_id, body.name, body.template_name
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Unknown template")
    return agent


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: UUID, ctx: OrgCtx) -> dict[str, Any]:
    agent = await agent_config_store.get_agent(ctx.org_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: UUID, config: IndustryPack, ctx: OrgCtx
) -> dict[str, str]:
    # Body validated as IndustryPack by FastAPI — bad configs 422 before we get here
    updated = await agent_config_store.update_agent_config(ctx.org_id, agent_id, config)
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")
    tenant_resolver.clear_cache()  # live calls pick up the new config immediately
    return {"status": "updated"}


@router.post("/agents/{agent_id}/publish")
async def publish_agent(agent_id: UUID, ctx: OrgCtx) -> dict[str, str]:
    """Create/update the Vapi assistant for this agent and mark it active."""
    agent = await agent_config_store.get_agent(ctx.org_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    pack = IndustryPack.model_validate(agent["config"])

    try:
        if agent["vapi_assistant_id"]:
            assistant_id = str(agent["vapi_assistant_id"])
            await vapi_client.update_assistant(
                assistant_id, pack, agent["name"], agent_id, ctx.org_id
            )
        else:
            assistant_id = await vapi_client.create_assistant(
                pack, agent["name"], agent_id, ctx.org_id
            )
    except vapi_client.VapiError as exc:
        raise HTTPException(
            status_code=503 if exc.status == 503 else 502, detail=str(exc)
        ) from exc

    await agent_config_store.set_vapi_assistant_id(ctx.org_id, agent_id, assistant_id)
    tenant_resolver.clear_cache()
    return {"vapi_assistant_id": assistant_id, "status": "active"}

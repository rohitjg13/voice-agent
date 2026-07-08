from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.services import agent_config_store
from orchestrator.services.dashboard_auth import OrgCtx
from packs._schema.pack import IndustryPack

router = APIRouter()


class PackCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    industry: str = Field(min_length=1, max_length=80)
    agent_name: str = Field(min_length=1, max_length=80)
    product_name: str = Field(min_length=1, max_length=120)


@router.get("/packs")
async def list_packs(ctx: OrgCtx) -> list[dict[str, Any]]:
    return await agent_config_store.list_custom_packs(ctx.org_id)


@router.post("/packs", status_code=201)
async def create_pack(body: PackCreate, ctx: OrgCtx) -> dict[str, Any]:
    pack = _build_empty_pack(body.name, body.industry, body.agent_name, body.product_name)
    ok = await agent_config_store.create_custom_pack(ctx.org_id, pack)
    if not ok:
        raise HTTPException(status_code=409, detail="A pack with this name already exists")
    return {"name": pack.name, "status": "created"}


@router.get("/packs/{name}")
async def get_pack(name: str, ctx: OrgCtx) -> dict[str, Any]:
    pack = await agent_config_store.get_custom_pack(ctx.org_id, name)
    if pack is None:
        raise HTTPException(status_code=404, detail="Pack not found")
    return pack.model_dump()


@router.put("/packs/{name}")
async def update_pack(name: str, config: IndustryPack, ctx: OrgCtx) -> dict[str, str]:
    updated = await agent_config_store.update_custom_pack(ctx.org_id, name, config)
    if not updated:
        raise HTTPException(status_code=404, detail="Pack not found")
    return {"status": "updated"}


@router.delete("/packs/{name}")
async def delete_pack(name: str, ctx: OrgCtx) -> dict[str, str]:
    deleted = await agent_config_store.delete_custom_pack(ctx.org_id, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pack not found")
    return {"status": "deleted"}


def _build_empty_pack(name: str, industry: str, agent_name: str, product_name: str) -> IndustryPack:
    return IndustryPack(
        name=name,
        version="0.1.0",
        industry=industry,
        agent={"name": agent_name, "voice_id": ""},
        product={"name": product_name, "description": "", "key_benefits": []},
        system_prompt_template=(
            "You are {{ agent.name }}, an AI calling about {{ product.name }}.\n"
            "{{ product.description }}\n\n"
            "Key benefits:\n{% for b in product.key_benefits %}- {{ b }}\n{% endfor %}\n\n"
            "Stay professional and compliant. Never say: {{ compliance.never_say | join(', ') }}.\n"
            "Required disclosure: {{ compliance.required_disclosure }}"
        ),
        stages={
            "opener": "Hello, is this [prospect name]? This is {{ agent.name }} calling on behalf of {{ product.name }}. How are you today?",
            "permission": "Do you have a moment to chat briefly?",
            "discovery_questions": [],
            "pitch_points": [],
            "close": "",
            "schedule": "",
        },
        objections=[],
        compliance={
            "never_say": [],
            "required_disclosure": "This call may be recorded for quality assurance.",
            "do_not_call_check": False,
        },
        scheduling={
            "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "working_hours": "09:00-17:00",
            "timezone": "America/Chicago",
        },
    )

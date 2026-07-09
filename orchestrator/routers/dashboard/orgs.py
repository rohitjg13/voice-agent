from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.services import org_store
from orchestrator.services.dashboard_auth import AuthCtx

router = APIRouter()


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/me")
async def me(ctx: AuthCtx) -> dict[str, Any]:
    return await org_store.get_me(ctx)


@router.post("/orgs", status_code=201)
async def create_org(body: OrgCreate, ctx: AuthCtx) -> dict[str, str]:
    if ctx.org_id is not None:
        raise HTTPException(status_code=409, detail="Already in an organization")
    org_id = await org_store.create_org(ctx.user_id, ctx.email, body.name)
    return {"org_id": str(org_id)}

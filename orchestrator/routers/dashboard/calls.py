from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from orchestrator.services import call_record_store
from orchestrator.services.dashboard_auth import OrgCtx

router = APIRouter()

_OUTCOMES = {"booked", "declined", "no_answer", "voicemail", "failed", "completed"}


@router.get("/calls")
async def list_calls(
    ctx: OrgCtx,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: datetime | None = None,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    if outcome is not None and outcome not in _OUTCOMES:
        raise HTTPException(status_code=422, detail="Unknown outcome")
    return await call_record_store.list_calls(
        ctx.org_id, limit=limit, before=before, outcome=outcome
    )


@router.get("/calls/{call_id}")
async def get_call(call_id: UUID, ctx: OrgCtx) -> dict[str, Any]:
    call = await call_record_store.get_call(ctx.org_id, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@router.get("/appointments")
async def list_appointments(ctx: OrgCtx) -> list[dict[str, Any]]:
    return await call_record_store.list_appointments(ctx.org_id)

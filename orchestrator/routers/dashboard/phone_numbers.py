from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.db import require_pool
from orchestrator.services import vapi_client
from orchestrator.services.dashboard_auth import OrgCtx

router = APIRouter()


class PhoneNumberCreate(BaseModel):
    area_code: str | None = Field(default=None, pattern=r"^\d{3}$")


@router.get("/phone-numbers")
async def list_phone_numbers(ctx: OrgCtx) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        """
        SELECT id, vapi_phone_number_id, e164, status, created_at
        FROM phone_numbers WHERE org_id = $1 ORDER BY created_at
        """,
        ctx.org_id,
    )
    return [dict(r) for r in rows]


@router.post("/phone-numbers", status_code=201)
async def buy_phone_number(body: PhoneNumberCreate, ctx: OrgCtx) -> dict[str, Any]:
    try:
        number = await vapi_client.buy_phone_number(body.area_code)
    except vapi_client.VapiError as exc:
        raise HTTPException(
            status_code=503 if exc.status == 503 else 502, detail=str(exc)
        ) from exc

    e164 = str(number.get("number") or number.get("e164") or "")
    pool = require_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO phone_numbers (org_id, vapi_phone_number_id, e164)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        ctx.org_id,
        str(number["id"]),
        e164,
    )
    return {"id": str(row["id"]), "vapi_phone_number_id": str(number["id"]), "e164": e164}

"""Org-scoped aggregates over the calls table — plain SQL GROUP BYs."""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from orchestrator.db import require_pool
from orchestrator.services.dashboard_auth import OrgCtx

router = APIRouter()

Days = Annotated[int, Query(ge=1, le=365)]


@router.get("/analytics/overview")
async def overview(ctx: OrgCtx, days: Days = 30) -> dict[str, Any]:
    pool = require_pool()
    totals = await pool.fetchrow(
        """
        SELECT COUNT(*)                          AS total_calls,
               COUNT(*) FILTER (WHERE booked)    AS booked,
               COALESCE(SUM(duration_seconds), 0) AS total_seconds,
               COALESCE(AVG(duration_seconds), 0) AS avg_seconds
        FROM calls
        WHERE org_id = $1 AND created_at > NOW() - make_interval(days => $2)
        """,
        ctx.org_id,
        days,
    )
    outcome_rows = await pool.fetch(
        """
        SELECT outcome, COUNT(*) AS n FROM calls
        WHERE org_id = $1 AND created_at > NOW() - make_interval(days => $2)
              AND outcome IS NOT NULL
        GROUP BY outcome
        """,
        ctx.org_id,
        days,
    )
    objection_rows = await pool.fetch(
        """
        SELECT obj, COUNT(*) AS n
        FROM calls, jsonb_array_elements_text(objections) AS obj
        WHERE org_id = $1 AND created_at > NOW() - make_interval(days => $2)
        GROUP BY obj ORDER BY n DESC LIMIT 5
        """,
        ctx.org_id,
        days,
    )
    total = totals["total_calls"] or 0
    booked = totals["booked"] or 0
    return {
        "total_calls": total,
        "booked": booked,
        "book_rate": round(booked / total, 3) if total else 0.0,
        "total_minutes": round((totals["total_seconds"] or 0) / 60, 1),
        "avg_duration_seconds": round(float(totals["avg_seconds"] or 0), 1),
        "outcomes": {r["outcome"]: r["n"] for r in outcome_rows},
        "top_objections": [{"objection": r["obj"], "count": r["n"]} for r in objection_rows],
    }


@router.get("/analytics/timeseries")
async def timeseries(ctx: OrgCtx, days: Days = 30) -> list[dict[str, Any]]:
    pool = require_pool()
    rows = await pool.fetch(
        """
        SELECT date_trunc('day', created_at) AS day,
               COUNT(*)                       AS calls,
               COUNT(*) FILTER (WHERE booked) AS booked
        FROM calls
        WHERE org_id = $1 AND created_at > NOW() - make_interval(days => $2)
        GROUP BY 1 ORDER BY 1
        """,
        ctx.org_id,
        days,
    )
    return [dict(r) for r in rows]

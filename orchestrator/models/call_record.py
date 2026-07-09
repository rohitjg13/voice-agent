from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CallRecord(BaseModel):
    """One completed call, persisted from the end-of-call webhook."""

    vapi_call_id: str
    org_id: UUID | None = None
    agent_id: UUID | None = None
    campaign_id: UUID | None = None
    lead_id: UUID | None = None
    direction: str = "outbound"
    customer_number: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    ended_reason: str | None = None
    stage_reached: str | None = None
    outcome: str | None = None
    booked: bool = False
    objections: list[str] = Field(default_factory=list)
    transcript: list[dict[str, str]] = Field(default_factory=list)
    summary: str | None = None
    cost_usd: float | None = None

from uuid import UUID

from pydantic import BaseModel


class Appointment(BaseModel):
    call_id: str
    pack_name: str
    org_id: UUID | None = None
    agent_id: UUID | None = None
    booked: bool = False
    prospect_name: str | None = None
    prospect_email: str | None = None
    requested_time: str | None = None  # raw text — "Thursday at 2pm"
    summary: str | None = None
    transcript: str | None = None

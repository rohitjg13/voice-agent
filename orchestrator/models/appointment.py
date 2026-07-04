from datetime import datetime

from pydantic import BaseModel


class Appointment(BaseModel):
    call_id: str
    pack_name: str
    booked: bool = False
    prospect_name: str | None = None
    prospect_email: str | None = None
    requested_time: str | None = None  # raw text — "Thursday at 2pm"
    summary: str | None = None
    transcript: str | None = None

    # Resolved from requested_time by the extractor; the calendar step needs a
    # concrete instant. end_time is derived at booking from the pack's duration.
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Set once a real calendar event has been created for this appointment.
    calendar_provider: str | None = None
    calendar_event_id: str | None = None
    calendar_event_url: str | None = None

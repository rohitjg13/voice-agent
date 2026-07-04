from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentPersona(BaseModel):
    name: str
    voice_id: str = ""  # ElevenLabs voice ID


class ProductInfo(BaseModel):
    name: str
    description: str
    key_benefits: list[str] = Field(default_factory=list)


class StageScripts(BaseModel):
    """Per-state scripts. All optional so packs can omit unused states."""

    opener: str = ""
    permission: str = ""
    discovery_questions: list[str] = Field(default_factory=list)
    pitch_points: list[str] = Field(default_factory=list)
    close: str = ""
    schedule: str = ""


class ObjectionEntry(BaseModel):
    id: str
    label: str
    patterns: list[str]  # trigger keywords / phrases
    responses: list[str]  # candidate reply templates
    max_strikes: int = 3


class ComplianceConfig(BaseModel):
    never_say: list[str] = Field(default_factory=list)
    required_disclosure: str = ""
    do_not_call_check: bool = True


class SchedulingConfig(BaseModel):
    """When the business can take meetings. Used to constrain proposed times."""

    working_days: list[str] = Field(
        default_factory=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    )
    working_hours: str = "9 AM to 5 PM"
    timezone: str = "America/Chicago"


class CalendarConfig(BaseModel):
    """Where a booked appointment lands as a real calendar event.

    The pack names only the provider and the *non-secret* target (which Cal.com
    event type / which Google calendar) so a single account can serve many
    industries. Credentials live in env (see orchestrator.config), never here.
    """

    # "none" keeps the pack DB-only; switch per-client to book real invites.
    provider: Literal["none", "cal_com", "google"] = "none"
    event_type_id: int | None = None  # Cal.com: the event type to book against
    calendar_id: str | None = None  # Google: the calendar to write the event to
    duration_minutes: int = 15


class IndustryPack(BaseModel):
    """Top-level schema for an industry pack YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    industry: str
    agent: AgentPersona
    product: ProductInfo
    # Jinja2 template rendered at call-start — may reference {{ agent.name }}, {{ product.name }}, etc.
    system_prompt_template: str
    stages: StageScripts
    objections: list[ObjectionEntry] = Field(default_factory=list)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)

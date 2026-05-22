from enum import StrEnum

from pydantic import BaseModel, Field


class ConversationState(StrEnum):
    OPENER = "OPENER"
    PERMISSION = "PERMISSION"
    DISCOVERY = "DISCOVERY"
    PITCH = "PITCH"
    OBJECTION = "OBJECTION"
    CLOSE = "CLOSE"
    SCHEDULE = "SCHEDULE"
    END = "END"


class Intent(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    OBJECTION = "objection"
    AGREE = "agree"
    QUESTION = "question"
    GOODBYE = "goodbye"
    NEUTRAL = "neutral"


class CallState(BaseModel):
    call_id: str
    pack_name: str
    stage: ConversationState = ConversationState.OPENER
    turn_count: int = 0
    discovery_turns: int = 0
    pitch_turns: int = 0
    # {objection_id: strike_count} — "generic" key used before step-8 classifier
    objection_strikes: dict[str, int] = Field(default_factory=dict)
    # Indices into pack.stages.discovery_questions already posed
    asked_question_indices: list[int] = Field(default_factory=list)
    # Where to return after an objection is handled
    pre_objection_stage: ConversationState = ConversationState.PITCH
    # Set by FSM when entering OBJECTION; used by objection handler
    current_objection_id: str = "none"
    # Compliance
    disclosure_given: bool = False
    compliance_violations: list[str] = Field(default_factory=list)
    # SCHEDULE sub-state — collected one at a time before END is allowed
    collected_email: str | None = None
    collected_name: str | None = None

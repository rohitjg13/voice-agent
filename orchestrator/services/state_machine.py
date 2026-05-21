"""
Pure FSM transition logic — no I/O, no side effects.

States:  OPENER → PERMISSION → DISCOVERY → PITCH → CLOSE → SCHEDULE → END
                                              ↑          ↑
                                         OBJECTION ──────┘
"""

from orchestrator.models.call_state import CallState, ConversationState, Intent

# Auto-advance thresholds
_DISCOVERY_TURNS_BEFORE_PITCH = 3
_PITCH_TURNS_BEFORE_CLOSE = 2
_DEFAULT_MAX_OBJECTION_STRIKES = 3


def transition(
    state: CallState,
    intent: Intent,
    objection_id: str = "generic",
) -> CallState:
    """Return a new CallState after applying the intent to the current stage."""
    s = state.model_copy(deep=True)
    s.turn_count += 1

    match s.stage:
        case ConversationState.OPENER:
            s.stage = ConversationState.PERMISSION

        case ConversationState.PERMISSION:
            s.stage = _from_permission(intent)

        case ConversationState.DISCOVERY:
            s.discovery_turns += 1
            s.stage = _from_discovery(s, intent)

        case ConversationState.PITCH:
            s.pitch_turns += 1
            if intent == Intent.OBJECTION:
                s.pre_objection_stage = ConversationState.PITCH
                s.stage = ConversationState.OBJECTION
            elif intent in (Intent.INTERESTED, Intent.AGREE):
                s.stage = ConversationState.CLOSE
            elif s.pitch_turns >= _PITCH_TURNS_BEFORE_CLOSE:
                s.stage = ConversationState.CLOSE

        case ConversationState.OBJECTION:
            s.stage = _from_objection(s, objection_id)

        case ConversationState.CLOSE:
            if intent == Intent.AGREE:
                s.stage = ConversationState.SCHEDULE
            elif intent == Intent.OBJECTION:
                s.pre_objection_stage = ConversationState.CLOSE
                s.stage = ConversationState.OBJECTION
            elif intent in (Intent.NOT_INTERESTED, Intent.GOODBYE):
                s.stage = ConversationState.END

        case ConversationState.SCHEDULE:
            s.stage = ConversationState.END

        case ConversationState.END:
            pass  # terminal — no transitions

    # Stamp the objection id whenever we land in OBJECTION
    if s.stage == ConversationState.OBJECTION:
        s.current_objection_id = objection_id

    return s


# ── helpers ──────────────────────────────────────────────────────────────────


def _from_permission(intent: Intent) -> ConversationState:
    if intent in (Intent.NOT_INTERESTED, Intent.GOODBYE):
        return ConversationState.END
    return ConversationState.DISCOVERY


def _from_discovery(state: CallState, intent: Intent) -> ConversationState:
    if intent == Intent.OBJECTION:
        state.pre_objection_stage = ConversationState.DISCOVERY
        return ConversationState.OBJECTION
    if intent in (Intent.INTERESTED, Intent.AGREE):
        return ConversationState.PITCH
    if state.discovery_turns >= _DISCOVERY_TURNS_BEFORE_PITCH:
        return ConversationState.PITCH
    return ConversationState.DISCOVERY


def _from_objection(state: CallState, objection_id: str) -> ConversationState:
    state.objection_strikes[objection_id] = (
        state.objection_strikes.get(objection_id, 0) + 1
    )
    total = sum(state.objection_strikes.values())
    if total >= _DEFAULT_MAX_OBJECTION_STRIKES:
        return ConversationState.END
    return state.pre_objection_stage

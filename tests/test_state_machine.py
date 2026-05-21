import pytest

from orchestrator.models.call_state import CallState, ConversationState, Intent
from orchestrator.services.state_machine import (
    _DISCOVERY_TURNS_BEFORE_PITCH,
    _PITCH_TURNS_BEFORE_CLOSE,
    transition,
)


def _state(stage: ConversationState = ConversationState.OPENER, **kwargs: object) -> CallState:
    return CallState(call_id="test", pack_name="dental_saas", stage=stage, **kwargs)


# ── OPENER ────────────────────────────────────────────────────────────────────

def test_opener_any_intent_goes_to_permission():
    for intent in Intent:
        s = transition(_state(ConversationState.OPENER), intent)
        assert s.stage == ConversationState.PERMISSION


def test_opener_increments_turn_count():
    s = transition(_state(ConversationState.OPENER), Intent.NEUTRAL)
    assert s.turn_count == 1


# ── PERMISSION ────────────────────────────────────────────────────────────────

def test_permission_positive_goes_to_discovery():
    for intent in (Intent.INTERESTED, Intent.NEUTRAL, Intent.QUESTION):
        s = transition(_state(ConversationState.PERMISSION), intent)
        assert s.stage == ConversationState.DISCOVERY, f"failed for {intent}"


def test_permission_negative_goes_to_end():
    for intent in (Intent.NOT_INTERESTED, Intent.GOODBYE):
        s = transition(_state(ConversationState.PERMISSION), intent)
        assert s.stage == ConversationState.END, f"failed for {intent}"


# ── DISCOVERY ─────────────────────────────────────────────────────────────────

def test_discovery_neutral_stays_in_discovery_early():
    s = transition(_state(ConversationState.DISCOVERY, discovery_turns=0), Intent.NEUTRAL)
    assert s.stage == ConversationState.DISCOVERY


def test_discovery_auto_advances_after_threshold():
    s = transition(
        _state(ConversationState.DISCOVERY, discovery_turns=_DISCOVERY_TURNS_BEFORE_PITCH - 1),
        Intent.NEUTRAL,
    )
    assert s.stage == ConversationState.PITCH


def test_discovery_interested_jumps_to_pitch():
    s = transition(_state(ConversationState.DISCOVERY, discovery_turns=0), Intent.INTERESTED)
    assert s.stage == ConversationState.PITCH


def test_discovery_objection_goes_to_objection():
    s = transition(_state(ConversationState.DISCOVERY), Intent.OBJECTION)
    assert s.stage == ConversationState.OBJECTION
    assert s.pre_objection_stage == ConversationState.DISCOVERY


# ── PITCH ─────────────────────────────────────────────────────────────────────

def test_pitch_objection_goes_to_objection():
    s = transition(_state(ConversationState.PITCH), Intent.OBJECTION)
    assert s.stage == ConversationState.OBJECTION
    assert s.pre_objection_stage == ConversationState.PITCH


def test_pitch_interested_goes_to_close():
    s = transition(_state(ConversationState.PITCH), Intent.INTERESTED)
    assert s.stage == ConversationState.CLOSE


def test_pitch_auto_advances_after_threshold():
    s = transition(
        _state(ConversationState.PITCH, pitch_turns=_PITCH_TURNS_BEFORE_CLOSE - 1),
        Intent.NEUTRAL,
    )
    assert s.stage == ConversationState.CLOSE


# ── OBJECTION ─────────────────────────────────────────────────────────────────

def test_objection_returns_to_pre_objection_stage():
    state = _state(ConversationState.OBJECTION, pre_objection_stage=ConversationState.PITCH)
    s = transition(state, Intent.NEUTRAL, objection_id="not_interested")
    assert s.stage == ConversationState.PITCH


def test_objection_increments_strike():
    state = _state(ConversationState.OBJECTION)
    s = transition(state, Intent.NEUTRAL, objection_id="not_interested")
    assert s.objection_strikes.get("not_interested") == 1


def test_objection_three_strikes_ends_call():
    state = _state(
        ConversationState.OBJECTION,
        objection_strikes={"not_interested": 2},
    )
    s = transition(state, Intent.NEUTRAL, objection_id="not_interested")
    assert s.stage == ConversationState.END


def test_objection_different_ids_accumulate_total():
    # 2 existing strikes on different objections → next one ends call
    state = _state(
        ConversationState.OBJECTION,
        objection_strikes={"not_interested": 1, "too_expensive": 1},
    )
    s = transition(state, Intent.NEUTRAL, objection_id="call_back_later")
    assert s.stage == ConversationState.END


# ── CLOSE ─────────────────────────────────────────────────────────────────────

def test_close_agree_goes_to_schedule():
    s = transition(_state(ConversationState.CLOSE), Intent.AGREE)
    assert s.stage == ConversationState.SCHEDULE


def test_close_objection_goes_to_objection():
    s = transition(_state(ConversationState.CLOSE), Intent.OBJECTION)
    assert s.stage == ConversationState.OBJECTION


def test_close_not_interested_ends_call():
    s = transition(_state(ConversationState.CLOSE), Intent.NOT_INTERESTED)
    assert s.stage == ConversationState.END


# ── SCHEDULE / END ────────────────────────────────────────────────────────────

def test_schedule_any_intent_goes_to_end():
    s = transition(_state(ConversationState.SCHEDULE), Intent.NEUTRAL)
    assert s.stage == ConversationState.END


def test_end_is_terminal():
    s = transition(_state(ConversationState.END), Intent.INTERESTED)
    assert s.stage == ConversationState.END


# ── immutability ──────────────────────────────────────────────────────────────

def test_transition_does_not_mutate_input():
    original = _state(ConversationState.OPENER)
    _ = transition(original, Intent.NEUTRAL)
    assert original.stage == ConversationState.OPENER
    assert original.turn_count == 0

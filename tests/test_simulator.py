from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models.call_state import ConversationState
from simulator.evaluator import aggregate, format_report
from simulator.runner import (
    Persona,
    SimResult,
    _flip_for_persona,
    _stream_to_text,
    get_persona,
    load_personas,
    run_simulation,
)


# ── persona loading ──────────────────────────────────────────────────────────

def test_load_personas_returns_at_least_10():
    personas = load_personas()
    assert len(personas) >= 10


def test_load_personas_have_required_fields():
    for p in load_personas():
        assert p.name and p.label and p.description and p.system_prompt


def test_get_persona_by_name():
    p = get_persona("hostile")
    assert p.label == "Hostile Prospect"


def test_get_persona_missing_raises():
    with pytest.raises(KeyError):
        get_persona("does_not_exist")


# ── role flipping ────────────────────────────────────────────────────────────

def test_flip_swaps_user_and_assistant():
    transcript = [
        {"role": "user", "content": "Hello?"},
        {"role": "assistant", "content": "Hi, this is Alex"},
        {"role": "user", "content": "Who?"},
    ]
    flipped = _flip_for_persona(transcript)
    assert flipped == [
        {"role": "assistant", "content": "Hello?"},
        {"role": "user", "content": "Hi, this is Alex"},
        {"role": "assistant", "content": "Who?"},
    ]


def test_flip_empty_list():
    assert _flip_for_persona([]) == []


# ── SSE parsing ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_to_text_assembles_content():
    sse_lines = [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        'data: {"choices":[{"delta":{"content":"Hello "}}]}',
        'data: {"choices":[{"delta":{"content":"world"}}]}',
        'data: {"choices":[{"delta":{}}]}',
        "data: [DONE]",
    ]

    class FakeResponse:
        async def aiter_lines(self):
            for line in sse_lines:
                yield line

    text = await _stream_to_text(FakeResponse())
    assert text == "Hello world"


@pytest.mark.asyncio
async def test_stream_to_text_skips_malformed_lines():
    sse_lines = [
        "event: ping",
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        "data: garbage{",
        "data: [DONE]",
    ]

    class FakeResponse:
        async def aiter_lines(self):
            for line in sse_lines:
                yield line

    text = await _stream_to_text(FakeResponse())
    assert text == "hi"


# ── full simulation (mocked agent + persona) ─────────────────────────────────

@pytest.mark.asyncio
async def test_run_simulation_completes(monkeypatch):
    """End-to-end with both the agent HTTP call and persona LLM mocked."""
    persona = Persona(
        name="test_p",
        label="Test",
        description="x",
        system_prompt="You are a test persona.",
    )

    # Mock the agent's HTTP turn to return canned responses
    agent_responses = iter([
        "Hi, is this the office manager?",
        "We help reduce no-shows by 40%.",
        "Great — Thursday at 2pm work? I'll send a calendar invite.",
    ])

    async def fake_agent_turn(client, transcript, call_id):
        try:
            return next(agent_responses)
        except StopIteration:
            return "Thanks for your time, goodbye."

    # Mock the persona LLM
    async def fake_persona_turn(persona, transcript):
        responses = iter(["Yes, who's calling?", "Sounds interesting.", "Yes, that works."])
        try:
            return next(responses)
        except StopIteration:
            return "Bye."

    monkeypatch.setattr("simulator.runner._agent_turn", fake_agent_turn)
    monkeypatch.setattr("simulator.runner._persona_turn", fake_persona_turn)

    result = await run_simulation(persona, max_turns=5)
    assert isinstance(result, SimResult)
    assert result.persona == "test_p"
    assert len(result.transcript) >= 4  # at least 2 exchanges


# ── evaluator ────────────────────────────────────────────────────────────────

def _result(persona: str, booked: bool, turns: int, violations: list[str] | None = None) -> SimResult:
    return SimResult(
        persona=persona,
        transcript=[],
        final_state=ConversationState.SCHEDULE if booked else ConversationState.END,
        turn_count=turns,
        reached_schedule=booked,
        compliance_violations=violations or [],
    )


def test_aggregate_empty_results():
    m = aggregate([])
    assert m.total == 0
    assert m.book_rate == 0.0


def test_aggregate_basic_metrics():
    results = [
        _result("a", booked=True, turns=4),
        _result("b", booked=False, turns=6),
        _result("c", booked=True, turns=5),
    ]
    m = aggregate(results)
    assert m.total == 3
    assert m.booked == 2
    assert m.book_rate == pytest.approx(2 / 3)
    assert m.avg_turns == pytest.approx(5.0)


def test_aggregate_counts_violations():
    results = [
        _result("a", booked=True, turns=3),
        _result("b", booked=False, turns=4, violations=["banned_word:promise", "banned_word:guarantee"]),
    ]
    m = aggregate(results)
    assert m.violations_total == 2
    assert m.violations_by_persona == {"b": ["banned_word:promise", "banned_word:guarantee"]}


def test_format_report_contains_summary():
    results = [_result("eager_adopter", booked=True, turns=3)]
    report = format_report(results)
    assert "Personas run" in report
    assert "eager_adopter" in report
    assert "booked" in report

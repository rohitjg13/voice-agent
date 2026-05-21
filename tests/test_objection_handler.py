import pytest

from orchestrator.models.call_state import CallState, ConversationState
from orchestrator.services.objection_handler import (
    ObjectionContext,
    find_objection_entry,
    handle_objection,
    select_response,
)
from packs.pack_loader import clear_cache, load_pack


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def pack():
    return load_pack("dental_saas")


def _objection_state(objection_id: str, strikes: dict[str, int] | None = None) -> CallState:
    return CallState(
        call_id="test",
        pack_name="dental_saas",
        stage=ConversationState.OBJECTION,
        current_objection_id=objection_id,
        objection_strikes=strikes or {objection_id: 1},
    )


# ── find_objection_entry ──────────────────────────────────────────────────────

def test_find_by_exact_id(pack):
    entry = find_objection_entry(pack, "too_expensive")
    assert entry is not None
    assert entry.id == "too_expensive"


def test_find_by_pattern_fallback(pack):
    entry = find_objection_entry(pack, "generic", message="We use Dentrix already")
    assert entry is not None
    assert entry.id == "already_have_software"


def test_find_generic_no_message_returns_none(pack):
    assert find_objection_entry(pack, "generic") is None


def test_find_unknown_id_no_message_returns_none(pack):
    assert find_objection_entry(pack, "does_not_exist") is None


def test_find_pattern_case_insensitive(pack):
    entry = find_objection_entry(pack, "generic", message="NOT INTERESTED AT ALL")
    assert entry is not None
    assert entry.id == "not_interested"


# ── select_response ───────────────────────────────────────────────────────────

def test_select_response_strike_1(pack):
    entry = next(o for o in pack.objections if o.id == "not_interested")
    resp = select_response(entry, strike_count=1)
    assert resp == entry.responses[0]


def test_select_response_strike_2(pack):
    entry = next(o for o in pack.objections if o.id == "not_interested")
    resp = select_response(entry, strike_count=2)
    assert resp == entry.responses[1]


def test_select_response_beyond_max_clamps_to_last(pack):
    entry = next(o for o in pack.objections if o.id == "not_interested")
    resp = select_response(entry, strike_count=99)
    assert resp == entry.responses[-1]


def test_select_response_strike_0_returns_first(pack):
    entry = next(o for o in pack.objections if o.id == "not_interested")
    resp = select_response(entry, strike_count=0)
    assert resp == entry.responses[0]


# ── handle_objection ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_known_objection(pack):
    state = _objection_state("too_expensive", {"too_expensive": 1})
    ctx = await handle_objection(pack, state)
    assert isinstance(ctx, ObjectionContext)
    assert ctx.objection_id == "too_expensive"
    assert ctx.strike_count == 1
    assert ctx.suggested_response  # non-empty
    assert ctx.retrieved_context == ""  # RAG not wired yet


@pytest.mark.asyncio
async def test_handle_objection_escalates_on_second_strike(pack):
    state = _objection_state("not_interested", {"not_interested": 2})
    ctx = await handle_objection(pack, state)
    entry = next(o for o in pack.objections if o.id == "not_interested")
    assert ctx.suggested_response == entry.responses[1]


@pytest.mark.asyncio
async def test_handle_generic_with_message_pattern_match(pack):
    state = _objection_state("generic", {"generic": 1})
    ctx = await handle_objection(pack, state, message="We already use Eaglesoft")
    assert ctx.objection_id == "already_have_software"


@pytest.mark.asyncio
async def test_handle_generic_no_message_uses_fallback(pack):
    state = _objection_state("generic", {"generic": 1})
    ctx = await handle_objection(pack, state, message="")
    assert ctx.label == "General objection"
    assert ctx.suggested_response


@pytest.mark.asyncio
async def test_handle_objection_max_strikes_reported(pack):
    state = _objection_state("call_back_later", {"call_back_later": 2})
    ctx = await handle_objection(pack, state)
    assert ctx.max_strikes == 2  # call_back_later has max_strikes=2
    assert ctx.strike_count == 2

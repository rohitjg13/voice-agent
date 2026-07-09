"""
Objection subsystem: taxonomy lookup, escalating response selection,
and a retrieval context slot (populated by RAG in step 10).
"""

from dataclasses import dataclass, field

from orchestrator.models.call_state import CallState
from orchestrator.services.rag import retrieve
from packs._schema.pack import IndustryPack, ObjectionEntry


@dataclass
class ObjectionContext:
    objection_id: str
    label: str
    strike_count: int
    max_strikes: int
    suggested_response: str
    retrieved_context: str = field(default="")  # RAG fills this in step 10


_GENERIC_FALLBACK_RESPONSES = [
    "I understand your concern — could you tell me a bit more about what's holding you back?",
    "That's a fair point. Many practices felt the same way before seeing the numbers. Would a quick demo help?",
    "I hear you. Thanks for your time — I'll let you go.",
]


def find_objection_entry(
    pack: IndustryPack,
    objection_id: str,
    message: str = "",
) -> ObjectionEntry | None:
    """Return the best-matching ObjectionEntry for the given id.

    Falls back to pattern matching when the id is 'generic', 'other', or unknown.
    """
    by_id = {o.id: o for o in pack.objections}

    if objection_id in by_id:
        return by_id[objection_id]

    # Pattern-based fallback
    if message:
        msg_lower = message.lower()
        for entry in pack.objections:
            if any(pattern.lower() in msg_lower for pattern in entry.patterns):
                return entry

    return None


def select_response(entry: ObjectionEntry, strike_count: int) -> str:
    """Pick the escalating response by strike index (1-based)."""
    if not entry.responses:
        return ""
    idx = min(max(0, strike_count - 1), len(entry.responses) - 1)
    return entry.responses[idx]


async def handle_objection(
    pack: IndustryPack,
    call_state: CallState,
    message: str = "",
) -> ObjectionContext:
    """Build ObjectionContext for the current OBJECTION turn, including RAG context."""
    objection_id = call_state.current_objection_id
    entry = find_objection_entry(pack, objection_id, message)

    if entry is None:
        strike_count = sum(call_state.objection_strikes.values()) or 1
        fallback_idx = min(strike_count - 1, len(_GENERIC_FALLBACK_RESPONSES) - 1)
        chunks = await retrieve(
            message or objection_id, pack.name, agent_id=call_state.agent_id
        )
        return ObjectionContext(
            objection_id=objection_id,
            label="General objection",
            strike_count=strike_count,
            max_strikes=3,
            suggested_response=_GENERIC_FALLBACK_RESPONSES[fallback_idx],
            retrieved_context="\n\n".join(chunks),
        )

    strike_count = call_state.objection_strikes.get(entry.id, 1)
    # Query: combine the objection label with the prospect's message for richer retrieval
    query = f"{entry.label}: {message}" if message else entry.label
    chunks = await retrieve(query, pack.name, agent_id=call_state.agent_id)
    return ObjectionContext(
        objection_id=entry.id,
        label=entry.label,
        strike_count=strike_count,
        max_strikes=entry.max_strikes,
        suggested_response=select_response(entry, strike_count),
        retrieved_context="\n\n".join(chunks),
    )

import pytest
from pydantic import ValidationError

from packs._schema.pack import (
    IndustryPack,
    ObjectionEntry,
)

MINIMAL_VALID = {
    "name": "test_pack",
    "version": "1.0",
    "industry": "test",
    "agent": {"name": "Alex"},
    "product": {
        "name": "TestProduct",
        "description": "A test product",
    },
    "system_prompt_template": "You are {{ agent.name }}, a rep for {{ product.name }}.",
    "stages": {},
}


def test_minimal_valid_pack():
    pack = IndustryPack(**MINIMAL_VALID)
    assert pack.name == "test_pack"
    assert pack.agent.name == "Alex"
    assert pack.compliance.do_not_call_check is True  # default
    assert pack.objections == []


def test_full_pack_roundtrip():
    data = {
        **MINIMAL_VALID,
        "agent": {"name": "Sarah", "voice_id": "voice-abc"},
        "product": {
            "name": "DentaFlow",
            "description": "Practice management SaaS",
            "key_benefits": ["Reduce no-shows by 40%", "Automate insurance verification"],
        },
        "stages": {
            "opener": "Hi, is this the office manager?",
            "permission": "I have a quick question about your scheduling workflow.",
            "discovery_questions": ["How many operatories do you have?"],
            "pitch_points": ["Integrates with your existing EHR"],
            "close": "Would Thursday or Friday work for a 15-minute demo?",
            "schedule": "Great — I'll send a calendar invite to your email.",
        },
        "objections": [
            {
                "id": "not_interested",
                "label": "Not interested",
                "patterns": ["not interested", "don't need this"],
                "responses": ["I completely understand — just one quick question before I let you go."],
                "max_strikes": 3,
            }
        ],
        "compliance": {
            "never_say": ["guaranteed", "promise"],
            "required_disclosure": "This call may be recorded.",
            "do_not_call_check": True,
        },
    }
    pack = IndustryPack(**data)
    assert pack.agent.voice_id == "voice-abc"
    assert len(pack.objections) == 1
    assert pack.objections[0].max_strikes == 3
    assert pack.compliance.never_say == ["guaranteed", "promise"]


def test_missing_required_name_raises():
    bad = {k: v for k, v in MINIMAL_VALID.items() if k != "name"}
    with pytest.raises(ValidationError) as exc:
        IndustryPack(**bad)
    assert "name" in str(exc.value)


def test_missing_agent_raises():
    bad = {k: v for k, v in MINIMAL_VALID.items() if k != "agent"}
    with pytest.raises(ValidationError):
        IndustryPack(**bad)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        IndustryPack(**MINIMAL_VALID, surprise_field="oops")


def test_objection_requires_patterns_and_responses():
    # empty lists are valid
    entry = ObjectionEntry(id="x", label="x", patterns=[], responses=[])
    assert entry.patterns == []

    # missing required fields raises
    with pytest.raises(ValidationError):
        ObjectionEntry(id="x", label="x")  # patterns and responses missing


def test_defaults():
    pack = IndustryPack(**MINIMAL_VALID)
    assert pack.stages.opener == ""
    assert pack.stages.discovery_questions == []
    assert pack.agent.voice_id == ""
    assert pack.product.key_benefits == []

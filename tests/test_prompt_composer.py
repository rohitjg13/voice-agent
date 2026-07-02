import pytest

from orchestrator.models.call_state import CallState, ConversationState
from orchestrator.services.prompt_composer import (
    render_stage_instruction,
    render_system_prompt,
)
from packs._schema.pack import (
    AgentPersona,
    ComplianceConfig,
    IndustryPack,
    ProductInfo,
    StageScripts,
)
from packs.pack_loader import clear_cache, load_pack


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def _minimal_pack(**overrides: object) -> IndustryPack:
    base: dict = {
        "name": "test",
        "version": "1.0",
        "industry": "test",
        "agent": AgentPersona(name="Jordan"),
        "product": ProductInfo(
            name="AcmePro",
            description="A great product",
            key_benefits=["Benefit A", "Benefit B"],
        ),
        "system_prompt_template": (
            "You are {{ agent.name }}, a rep for {{ product.name }}. "
            "Description: {{ product.description }}."
        ),
        "stages": StageScripts(),
        "compliance": ComplianceConfig(never_say=["guarantee"], required_disclosure="Recorded."),
    }
    base.update(overrides)
    return IndustryPack(**base)


def test_agent_name_rendered():
    pack = _minimal_pack()
    prompt = render_system_prompt(pack)
    assert "Jordan" in prompt


def test_product_name_rendered():
    pack = _minimal_pack()
    prompt = render_system_prompt(pack)
    assert "AcmePro" in prompt


def test_dental_saas_render_contains_key_fields():
    pack = load_pack("dental_saas")
    prompt = render_system_prompt(pack)
    assert "Alex" in prompt
    assert "DentaFlow" in prompt
    assert "guaranteed" in prompt  # compliance.never_say
    assert "recorded" in prompt.lower()  # required_disclosure


def test_dental_saas_benefits_rendered():
    pack = load_pack("dental_saas")
    prompt = render_system_prompt(pack)
    assert "no-shows" in prompt.lower()


def test_undefined_variable_raises():
    pack = _minimal_pack(
        system_prompt_template="Hello {{ nonexistent_var }}."
    )
    with pytest.raises(ValueError, match="Failed to render"):
        render_system_prompt(pack)


def test_output_is_stripped():
    pack = _minimal_pack(system_prompt_template="  Hello {{ agent.name }}.  \n")
    prompt = render_system_prompt(pack)
    assert prompt == "Hello Jordan."


def test_sandbox_blocks_python_internals():
    pack = _minimal_pack(
        system_prompt_template="{{ agent.__class__.__mro__ }}"
    )
    with pytest.raises(ValueError, match="Failed to render"):
        render_system_prompt(pack)


# ── discovery question rotation ───────────────────────────────────────────────


def _discovery_state(turns: int) -> CallState:
    return CallState(
        call_id="c1",
        pack_name="dental_saas",
        stage=ConversationState.DISCOVERY,
        discovery_turns=turns,
    )


def test_discovery_asks_different_question_each_turn():
    pack = load_pack("dental_saas")
    questions = pack.stages.discovery_questions
    first = render_stage_instruction(pack, _discovery_state(0))
    second = render_stage_instruction(pack, _discovery_state(1))
    assert questions[0] in first
    assert questions[1] in second
    assert questions[0] not in second


def test_discovery_exhausted_falls_back_to_followup():
    pack = load_pack("dental_saas")
    instruction = render_stage_instruction(pack, _discovery_state(99))
    assert "follow-up" in instruction

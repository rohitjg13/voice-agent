import pytest

from orchestrator.services.prompt_composer import render_system_prompt
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

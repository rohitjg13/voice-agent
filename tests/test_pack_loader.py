import pytest

from packs.pack_loader import clear_cache, load_pack


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def test_dental_saas_loads():
    pack = load_pack("dental_saas")
    assert pack.name == "dental_saas"
    assert pack.industry == "dental"
    assert pack.agent.name == "Alex"


def test_dental_saas_product():
    pack = load_pack("dental_saas")
    assert pack.product.name == "DentaFlow"
    assert len(pack.product.key_benefits) >= 3


def test_dental_saas_stages_populated():
    pack = load_pack("dental_saas")
    assert pack.stages.opener
    assert pack.stages.close
    assert len(pack.stages.discovery_questions) >= 3
    assert len(pack.stages.pitch_points) >= 2


def test_dental_saas_objections():
    pack = load_pack("dental_saas")
    assert len(pack.objections) == 5
    ids = {o.id for o in pack.objections}
    assert ids == {"not_interested", "already_have_software", "too_expensive", "call_back_later", "gatekeeper"}


def test_objection_responses_nonempty():
    pack = load_pack("dental_saas")
    for obj in pack.objections:
        assert obj.responses, f"objection '{obj.id}' has no responses"
        assert obj.patterns, f"objection '{obj.id}' has no patterns"


def test_compliance_fields():
    pack = load_pack("dental_saas")
    assert "guaranteed" in pack.compliance.never_say
    assert pack.compliance.required_disclosure
    assert pack.compliance.do_not_call_check is True


def test_system_prompt_template_present():
    pack = load_pack("dental_saas")
    assert "{{ agent.name }}" in pack.system_prompt_template
    assert "{{ product.key_benefits }}" in pack.system_prompt_template or "key_benefits" in pack.system_prompt_template


def test_caching_returns_same_object():
    pack_a = load_pack("dental_saas")
    pack_b = load_pack("dental_saas")
    assert pack_a is pack_b


def test_force_reload_refreshes_cache():
    pack_a = load_pack("dental_saas")
    pack_b = load_pack("dental_saas", force_reload=True)
    assert pack_a is not pack_b
    assert pack_a == pack_b


def test_missing_pack_raises_file_not_found():
    with pytest.raises(FileNotFoundError, match="No pack found"):
        load_pack("nonexistent_pack")

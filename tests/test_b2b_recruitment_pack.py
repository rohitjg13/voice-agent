"""
Extensibility proof: a second industry pack with zero code changes.
Verifies that b2b_recruitment loads, renders, and behaves distinctly from dental_saas.
"""

import pytest

from orchestrator.services.prompt_composer import render_system_prompt
from packs.pack_loader import clear_cache, load_pack


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def test_b2b_pack_loads():
    pack = load_pack("b2b_recruitment")
    assert pack.name == "b2b_recruitment"
    assert pack.industry == "b2b_recruitment"
    assert pack.agent.name == "Jordan"


def test_b2b_pack_product():
    pack = load_pack("b2b_recruitment")
    assert pack.product.name == "TalentFlow"
    assert any("time-to-fill" in b.lower() for b in pack.product.key_benefits)


def test_b2b_pack_objections_distinct_from_dental():
    b2b = load_pack("b2b_recruitment")
    dental = load_pack("dental_saas")

    b2b_ids = {o.id for o in b2b.objections}
    dental_ids = {o.id for o in dental.objections}

    # Some overlap (not_interested, too_expensive, gatekeeper, call_back_later)
    # but b2b has unique ones
    assert "internal_team_only" in b2b_ids
    assert "internal_team_only" not in dental_ids
    assert "already_have_ats" in b2b_ids
    assert "already_have_ats" not in dental_ids


def test_b2b_pack_stages():
    pack = load_pack("b2b_recruitment")
    assert pack.stages.opener
    assert pack.stages.close
    # Discovery questions are industry-specific
    questions = " ".join(pack.stages.discovery_questions).lower()
    assert "recruiter" in questions or "ats" in questions or "hiring" in questions


def test_b2b_pack_renders_distinct_system_prompt():
    b2b_prompt = render_system_prompt(load_pack("b2b_recruitment"))
    dental_prompt = render_system_prompt(load_pack("dental_saas"))

    assert "TalentFlow" in b2b_prompt
    assert "DentaFlow" not in b2b_prompt
    assert "Jordan" in b2b_prompt
    assert "Alex" not in b2b_prompt

    # Industry-specific terminology
    assert "recruiting" in b2b_prompt.lower() or "candidate" in b2b_prompt.lower()
    assert "dental" not in b2b_prompt.lower()

    # And dental prompt is genuinely different
    assert "DentaFlow" in dental_prompt
    assert "TalentFlow" not in dental_prompt


def test_b2b_pack_compliance():
    pack = load_pack("b2b_recruitment")
    assert "guaranteed" in pack.compliance.never_say
    assert "GDPR compliant" in pack.compliance.never_say
    assert pack.compliance.required_disclosure
    assert pack.compliance.do_not_call_check is True


def test_both_packs_loadable_independently():
    """Sanity: loading both packs in any order produces correct results."""
    a = load_pack("dental_saas")
    b = load_pack("b2b_recruitment")
    assert a.name != b.name
    assert a.agent.name != b.agent.name
    assert a.product.name != b.product.name


def test_b2b_knowledge_docs_exist():
    from pathlib import Path

    docs_dir = Path(__file__).parent.parent / "packs/b2b_recruitment/knowledge"
    docs = list(docs_dir.glob("*.md"))
    assert len(docs) >= 2
    names = {d.name for d in docs}
    assert "objection_faq.md" in names
    assert "product_faq.md" in names

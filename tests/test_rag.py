from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.services.rag import chunk_text, retrieve

# ── chunk_text (pure) ─────────────────────────────────────────────────────────

def test_chunk_splits_on_blank_lines():
    text = (
        "First paragraph with enough text to exceed the minimum character threshold for inclusion.\n\n"
        "Second paragraph also with enough text to exceed the minimum character threshold here."
    )
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert "First" in chunks[0]
    assert "Second" in chunks[1]


def test_chunk_filters_short_paragraphs():
    text = "OK\n\nThis is a longer paragraph that meets the minimum character requirement for inclusion in chunks."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "longer" in chunks[0]


def test_chunk_splits_long_paragraphs_by_sentence():
    long_para = ". ".join(["This is a sentence that is reasonably long"] * 20)
    chunks = chunk_text(long_para, max_chars=200)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 210  # allow small overrun from last sentence


def test_chunk_empty_text_returns_empty():
    assert chunk_text("") == []


def test_chunk_only_whitespace_returns_empty():
    assert chunk_text("   \n\n   \n\n  ") == []


def test_chunk_single_paragraph():
    text = "This is a single paragraph with enough characters to be included in the chunks list."
    chunks = chunk_text(text)
    assert chunks == [text]


def test_chunk_knowledge_doc_produces_multiple_chunks():
    from pathlib import Path
    doc = Path(__file__).parent.parent / "packs/dental_saas/knowledge/objection_faq.md"
    text = doc.read_text()
    chunks = chunk_text(text)
    assert len(chunks) >= 5
    for c in chunks:
        assert len(c) >= 50


# ── retrieve (mocked) ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_openai_key(monkeypatch):
    monkeypatch.setattr("orchestrator.services.rag.settings.openai_api_key", "")
    result = await retrieve("test query", "dental_saas")
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_database_url(monkeypatch):
    monkeypatch.setattr("orchestrator.services.rag.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("orchestrator.services.rag.settings.database_url", "")
    result = await retrieve("test query", "dental_saas")
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_pool(monkeypatch):
    monkeypatch.setattr("orchestrator.services.rag.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("orchestrator.services.rag.settings.database_url", "postgresql://localhost/test")
    # Pool is None (db not initialised)
    with patch("orchestrator.services.rag.get_pool", return_value=None):
        result = await retrieve("test query", "dental_saas")
    assert result == []


def _pool_mock(fetch_return: list | Exception) -> MagicMock:
    """Return a pool mock whose acquire() works as an async context manager."""
    fake_conn = AsyncMock()
    if isinstance(fetch_return, Exception):
        fake_conn.fetch = AsyncMock(side_effect=fetch_return)
    else:
        fake_conn.fetch = AsyncMock(return_value=fetch_return)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


@pytest.mark.asyncio
async def test_retrieve_returns_content_on_success(monkeypatch):
    monkeypatch.setattr("orchestrator.services.rag.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("orchestrator.services.rag.settings.database_url", "postgresql://localhost/test")

    pool = _pool_mock([{"content": "ROI is 17x"}, {"content": "Setup takes 2 days"}])
    with (
        patch("orchestrator.services.rag.get_pool", return_value=pool),
        patch("orchestrator.services.rag.embed", new=AsyncMock(return_value=[0.1] * 1536)),
    ):
        result = await retrieve("too expensive", "dental_saas", top_k=2)

    assert result == ["ROI is 17x", "Setup takes 2 days"]


@pytest.mark.asyncio
async def test_retrieve_handles_db_error_gracefully(monkeypatch):
    monkeypatch.setattr("orchestrator.services.rag.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("orchestrator.services.rag.settings.database_url", "postgresql://localhost/test")

    pool = _pool_mock(Exception("connection refused"))
    with (
        patch("orchestrator.services.rag.get_pool", return_value=pool),
        patch("orchestrator.services.rag.embed", new=AsyncMock(return_value=[0.1] * 1536)),
    ):
        result = await retrieve("query", "dental_saas")

    assert result == []


# ── objection handler with retrieval ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_objection_populates_retrieved_context():
    from orchestrator.models.call_state import CallState, ConversationState
    from orchestrator.services.objection_handler import handle_objection
    from packs.pack_loader import clear_cache, load_pack

    clear_cache()
    pack = load_pack("dental_saas")
    state = CallState(
        call_id="test",
        pack_name="dental_saas",
        stage=ConversationState.OBJECTION,
        current_objection_id="too_expensive",
        objection_strikes={"too_expensive": 1},
    )

    with patch(
        "orchestrator.services.objection_handler.retrieve",
        new=AsyncMock(return_value=["ROI is 17x.", "Free 30-day trial available."]),
    ):
        ctx = await handle_objection(pack, state, "How much does it cost?")

    assert "ROI is 17x." in ctx.retrieved_context
    assert "Free 30-day trial" in ctx.retrieved_context
    clear_cache()

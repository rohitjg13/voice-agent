"""
RAG pipeline: chunk → embed → retrieve.
All functions degrade gracefully when OpenAI or DB is unconfigured.
"""

import structlog
from openai import AsyncOpenAI

from orchestrator.config import settings
from orchestrator.db import get_pool

logger = structlog.get_logger()


# ── chunking ─────────────────────────────────────────────────────────────────


def chunk_text(text: str, min_chars: int = 50, max_chars: int = 800) -> list[str]:
    """Split text into paragraph-based chunks. Long paragraphs are split by sentence."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []

    for para in paragraphs:
        if len(para) < min_chars:
            continue
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            # Split on sentence boundaries
            sentences = para.replace(". ", ".\n").replace("? ", "?\n").split("\n")
            current = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current) + len(sent) + 1 <= max_chars:
                    current = (current + " " + sent).strip() if current else sent
                else:
                    if current:
                        chunks.append(current)
                    current = sent
            if current:
                chunks.append(current)

    return chunks


# ── embedding ─────────────────────────────────────────────────────────────────


async def embed(text: str) -> list[float]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text.replace("\n", " "),
    )
    return response.data[0].embedding


# ── retrieval ─────────────────────────────────────────────────────────────────


async def retrieve(query: str, pack_name: str, top_k: int | None = None) -> list[str]:
    """Return the top-k most relevant content chunks for the query.

    Returns [] when OpenAI or DB is not configured — callers degrade gracefully.
    """
    if not settings.openai_api_key or not settings.database_url:
        return []

    pool = get_pool()
    if pool is None:
        return []

    k = top_k or settings.rag_top_k

    try:
        embedding = await embed(query)
        embedding_str = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content
                FROM knowledge_chunks
                WHERE pack_name = $1
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                pack_name,
                embedding_str,
                k,
            )
        return [row["content"] for row in rows]

    except Exception as exc:
        logger.warning("rag_retrieve_error", error=str(exc))
        return []

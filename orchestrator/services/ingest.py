"""
Knowledge ingestion CLI.
Usage: python -m orchestrator.services.ingest dental_saas
"""

import asyncio
import sys
from pathlib import Path

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from orchestrator.config import settings
from orchestrator.services.rag import chunk_text, embed

logger = structlog.get_logger()

_KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "packs"


async def ingest_pack(pack_name: str) -> None:
    knowledge_dir = _KNOWLEDGE_DIR / pack_name / "knowledge"
    if not knowledge_dir.exists():
        raise FileNotFoundError(f"No knowledge dir at {knowledge_dir}")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn, ssl="require")
    await register_vector(conn)

    # Ensure table exists
    await conn.execute(
        """
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pack_name TEXT NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1536),
            metadata JSONB DEFAULT '{}'
        );
        """
    )

    docs = list(knowledge_dir.glob("*.md"))
    if not docs:
        logger.warning("ingest_no_docs", pack=pack_name)
        return

    total = 0
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        logger.info("ingest_doc", file=doc.name, chunks=len(chunks))

        for chunk in chunks:
            embedding = await embed(chunk)
            await conn.execute(
                """
                INSERT INTO knowledge_chunks (pack_name, source, content, embedding)
                VALUES ($1, $2, $3, $4)
                """,
                pack_name,
                doc.name,
                chunk,
                embedding,
            )
            total += 1

    await conn.close()
    logger.info("ingest_complete", pack=pack_name, total_chunks=total)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m orchestrator.services.ingest <pack_name>")
        sys.exit(1)
    asyncio.run(ingest_pack(sys.argv[1]))

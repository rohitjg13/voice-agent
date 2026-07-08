"""Per-agent knowledge base uploads → chunk → embed → pgvector rows."""

import re
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, UploadFile

from orchestrator.config import settings
from orchestrator.db import require_pool
from orchestrator.services import agent_config_store, rag
from orchestrator.services.dashboard_auth import OrgCtx

logger = structlog.get_logger()

router = APIRouter()

_SOURCE_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_MAX_UPLOAD_BYTES = 200_000
_ALLOWED_SUFFIXES = (".md", ".txt")


async def _owned_agent(ctx: OrgCtx, agent_id: UUID) -> dict[str, Any]:
    agent = await agent_config_store.get_agent(ctx.org_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/agents/{agent_id}/knowledge", status_code=201)
async def upload_knowledge(
    agent_id: UUID, file: UploadFile, ctx: OrgCtx
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Embeddings not configured")
    agent = await _owned_agent(ctx, agent_id)

    source = _SOURCE_SAFE_RE.sub("_", file.filename or "upload.txt")[:120]
    if not source.endswith(_ALLOWED_SUFFIXES):
        raise HTTPException(status_code=400, detail="Only .md and .txt files")

    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (200 KB max)")

    chunks = rag.chunk_text(data.decode("utf-8", errors="replace"))
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable content")

    pack_name = agent["config"]["name"]
    pool = require_pool()
    # Re-upload of the same filename replaces its chunks
    await pool.execute(
        "DELETE FROM knowledge_chunks WHERE agent_id = $1 AND source = $2",
        agent_id,
        source,
    )
    for chunk in chunks:
        embedding = await rag.embed(chunk)
        embedding_str = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
        await pool.execute(
            """
            INSERT INTO knowledge_chunks
                (pack_name, source, content, embedding, org_id, agent_id)
            VALUES ($1, $2, $3, $4::vector, $5, $6)
            """,
            pack_name,
            source,
            chunk,
            embedding_str,
            ctx.org_id,
            agent_id,
        )
    logger.info("knowledge_uploaded", agent_id=str(agent_id), source=source, chunks=len(chunks))
    return {"source": source, "chunks": len(chunks)}


@router.get("/agents/{agent_id}/knowledge")
async def list_knowledge(agent_id: UUID, ctx: OrgCtx) -> list[dict[str, Any]]:
    await _owned_agent(ctx, agent_id)
    pool = require_pool()
    rows = await pool.fetch(
        """
        SELECT source, COUNT(*) AS chunks
        FROM knowledge_chunks WHERE agent_id = $1
        GROUP BY source ORDER BY source
        """,
        agent_id,
    )
    return [{"source": r["source"], "chunks": r["chunks"]} for r in rows]


@router.delete("/agents/{agent_id}/knowledge/{source}", status_code=204)
async def delete_knowledge(agent_id: UUID, source: str, ctx: OrgCtx) -> None:
    await _owned_agent(ctx, agent_id)
    pool = require_pool()
    await pool.execute(
        "DELETE FROM knowledge_chunks WHERE agent_id = $1 AND source = $2",
        agent_id,
        _SOURCE_SAFE_RE.sub("_", source)[:120],
    )

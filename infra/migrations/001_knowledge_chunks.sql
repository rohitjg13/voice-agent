-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge chunks for RAG retrieval
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pack_name   TEXT        NOT NULL,
    source      TEXT        NOT NULL,           -- filename, e.g. "objection_faq.md"
    content     TEXT        NOT NULL,
    embedding   vector(1536),                   -- text-embedding-3-small
    metadata    JSONB       DEFAULT '{}'
);

-- IVFFlat index for approximate nearest-neighbour search
-- lists = sqrt(row_count); tune after ingest
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
    ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Filter-first index so pack_name WHERE clause is cheap
CREATE INDEX IF NOT EXISTS knowledge_chunks_pack_idx
    ON knowledge_chunks (pack_name);

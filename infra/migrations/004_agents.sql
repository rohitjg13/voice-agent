-- 004: pack templates (read-only seeds of the YAML packs) + per-tenant agents.

CREATE TABLE pack_templates (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL UNIQUE,          -- 'dental_saas', 'b2b_recruitment'
    version    TEXT NOT NULL,
    config     JSONB NOT NULL,                -- full IndustryPack dump
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE agents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    template_name     TEXT,                   -- provenance only
    config            JSONB NOT NULL,         -- IndustryPack-validated
    vapi_assistant_id TEXT UNIQUE,            -- set on publish
    status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX agents_org_idx ON agents (org_id);

-- Tenant scoping on existing tables. NULL = legacy YAML-pack rows.
ALTER TABLE knowledge_chunks ADD COLUMN org_id UUID, ADD COLUMN agent_id UUID;
CREATE INDEX knowledge_chunks_agent_idx ON knowledge_chunks (agent_id);

ALTER TABLE appointments ADD COLUMN org_id UUID, ADD COLUMN agent_id UUID;
CREATE INDEX appointments_org_idx ON appointments (org_id, created_at DESC);

ALTER TABLE pack_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;

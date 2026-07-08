-- 005: per-call records for logs + analytics, fed by the end-of-call webhook.

CREATE TABLE calls (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID REFERENCES organizations(id) ON DELETE CASCADE,  -- NULL = legacy
    agent_id         UUID REFERENCES agents(id) ON DELETE SET NULL,
    campaign_id      UUID,                    -- FK added in 007
    lead_id          UUID,
    vapi_call_id     TEXT NOT NULL UNIQUE,
    direction        TEXT NOT NULL DEFAULT 'outbound',
    customer_number  TEXT,
    started_at       TIMESTAMPTZ,
    ended_at         TIMESTAMPTZ,
    duration_seconds INT,
    ended_reason     TEXT,
    stage_reached    TEXT,                    -- final Redis CallState stage
    outcome          TEXT CHECK (outcome IN ('booked', 'declined', 'no_answer', 'voicemail', 'failed', 'completed')),
    booked           BOOLEAN NOT NULL DEFAULT FALSE,
    objections       JSONB NOT NULL DEFAULT '[]',
    transcript       JSONB,                   -- [{role, content}]
    summary          TEXT,
    cost_usd         NUMERIC(8,4),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX calls_org_created_idx ON calls (org_id, created_at DESC);
CREATE INDEX calls_campaign_idx ON calls (campaign_id);

ALTER TABLE calls ENABLE ROW LEVEL SECURITY;

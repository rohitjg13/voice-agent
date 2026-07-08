-- 007: phone numbers, campaigns, leads (outbound dialing).

CREATE TABLE phone_numbers (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vapi_phone_number_id TEXT NOT NULL UNIQUE,
    e164                 TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'active',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    agent_id        UUID NOT NULL REFERENCES agents(id),
    phone_number_id UUID REFERENCES phone_numbers(id),
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'running', 'paused', 'completed')),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX campaigns_org_idx ON campaigns (org_id);

CREATE TABLE leads (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    campaign_id  UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name         TEXT,
    company      TEXT,
    email        TEXT,
    phone_e164   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'calling', 'completed', 'failed', 'no_answer', 'dnc')),
    vapi_call_id TEXT,
    attempts     INT NOT NULL DEFAULT 0,
    last_error   TEXT,
    claimed_at   TIMESTAMPTZ,                 -- stuck-call reaper watches this
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (campaign_id, phone_e164)
);
CREATE INDEX leads_dial_idx ON leads (campaign_id, status);
CREATE INDEX leads_vapi_call_idx ON leads (vapi_call_id);

ALTER TABLE calls
    ADD CONSTRAINT calls_campaign_fk FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;

ALTER TABLE phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

-- 006: plans + subscriptions (stub billing — Stripe slots into provider columns later).

CREATE TABLE plans (
    id          TEXT PRIMARY KEY,             -- 'trial' | 'starter' | 'growth'
    name        TEXT NOT NULL,
    price_cents INT NOT NULL DEFAULT 0,
    limits      JSONB NOT NULL
);

CREATE TABLE subscriptions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   UUID NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    plan_id                  TEXT NOT NULL REFERENCES plans(id),
    status                   TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'past_due')),
    provider                 TEXT NOT NULL DEFAULT 'stub',   -- 'stripe' later
    provider_subscription_id TEXT,
    current_period_start     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_period_end       TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 days',
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO plans (id, name, price_cents, limits) VALUES
    ('trial',   'Trial',    0,     '{"max_agents": 1,  "included_minutes": 30,   "max_active_campaigns": 1,  "max_leads_per_campaign": 25}'),
    ('starter', 'Starter',  9900,  '{"max_agents": 2,  "included_minutes": 500,  "max_active_campaigns": 2,  "max_leads_per_campaign": 500}'),
    ('growth',  'Growth',   29900, '{"max_agents": 10, "included_minutes": 2500, "max_active_campaigns": 10, "max_leads_per_campaign": 5000}');

ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

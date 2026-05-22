-- Appointments captured from completed calls
CREATE TABLE IF NOT EXISTS appointments (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id         TEXT         NOT NULL UNIQUE,
    pack_name       TEXT         NOT NULL,
    booked          BOOLEAN      NOT NULL DEFAULT FALSE,
    prospect_name   TEXT,
    prospect_email  TEXT,
    requested_time  TEXT,        -- raw, e.g. "Thursday at 2pm"
    summary         TEXT,
    transcript      TEXT,
    metadata        JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS appointments_pack_idx       ON appointments (pack_name);
CREATE INDEX IF NOT EXISTS appointments_booked_idx     ON appointments (booked);
CREATE INDEX IF NOT EXISTS appointments_created_at_idx ON appointments (created_at DESC);

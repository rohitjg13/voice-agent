-- Real calendar integration: resolved meeting time + created event reference.
-- Additive and idempotent — safe to run on an existing appointments table.
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS start_time         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS end_time           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS calendar_provider  TEXT,   -- 'cal_com' | 'google'
    ADD COLUMN IF NOT EXISTS calendar_event_id  TEXT,
    ADD COLUMN IF NOT EXISTS calendar_event_url TEXT;

CREATE INDEX IF NOT EXISTS appointments_start_time_idx ON appointments (start_time);

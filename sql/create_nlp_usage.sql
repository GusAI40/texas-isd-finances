-- Shared spend ceiling for /query.
--
-- Why this exists
-- ---------------
-- Every /query call costs a paid OpenAI request. The limiter in src/api.py
-- kept its counters in PROCESS MEMORY, which on Vercel means each warm
-- instance enforced its own ceiling independently. A "60 per minute" global
-- limit was really "60 per minute PER INSTANCE", and the platform starts as
-- many instances as traffic demands — so the actual bound was the number of
-- instances an attacker could provoke, which is not a bound at all. The
-- per-IP limit does not help either: X-Forwarded-For is client-supplied, so
-- one attacker presents a fresh IP per request.
--
-- A counter has to live somewhere every instance can see. The database is
-- already there, so it goes here.
--
-- The daily cap is the one that actually protects the bill. A per-minute
-- ceiling only smooths bursts; a runaway script inside that ceiling still
-- bills 86,400 calls a day.
--
-- Apply with sql/create_tables.sql, or on its own — it is idempotent.

CREATE TABLE IF NOT EXISTS public.nlp_usage (
    window_kind  text        NOT NULL,        -- 'minute' or 'day'
    window_start timestamptz NOT NULL,
    calls        integer     NOT NULL DEFAULT 0,
    PRIMARY KEY (window_kind, window_start)
);

COMMENT ON TABLE public.nlp_usage IS
    'Cross-instance call counters for /query. Written by the API''s own '
    'connection, never by the NLP role — nlp_reader has no access here and '
    'must not: it is the thing being metered.';

-- This is internal accounting, not public data. The two API roles get
-- nothing, and RLS with no policy denies anything that slips past a missing
-- grant. The app writes with the owner connection (SUPABASE_DB_URL), which
-- is not subject to RLS.
REVOKE ALL ON public.nlp_usage FROM anon, authenticated;
ALTER TABLE public.nlp_usage ENABLE ROW LEVEL SECURITY;

-- nlp_reader is the least-privilege role that /query's language model runs
-- as. It must never be able to read its own meter, let alone edit it.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlp_reader') THEN
        REVOKE ALL ON public.nlp_usage FROM nlp_reader;
    END IF;
END
$$;

-- Old windows are dead weight. Anything past a week is history nobody reads.
CREATE INDEX IF NOT EXISTS idx_nlp_usage_start ON public.nlp_usage (window_start);

-- Housekeeping, safe to run any time:
--   DELETE FROM public.nlp_usage WHERE window_start < now() - interval '7 days';

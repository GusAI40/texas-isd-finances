-- Storage for the Texas ISD Intelligence daily research.
--
-- Serverless functions have a read-only filesystem, so the daily cron cannot
-- write its briefing to static/. It writes here instead, and /briefing reads
-- the latest row. Idempotent and safe to run more than once.
--
-- Apply with sql/create_tables.sql, or on its own.

CREATE TABLE IF NOT EXISTS public.isd_briefings (
    run_date   date        PRIMARY KEY,        -- one briefing per UTC day; the idempotency key
    payload    jsonb       NOT NULL,           -- the full briefing document
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.isd_briefings IS
    'Daily ISD intelligence briefings. run_date is the idempotency key: the '
    'cron upserts, so a replay on the same day overwrites rather than duplicates.';

-- The review queue, split out so a human can work it without loading a whole
-- briefing. A finding lands here when its district could not be resolved with
-- confidence, or when it contradicts stored data.
CREATE TABLE IF NOT EXISTS public.isd_review_queue (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_date     date        NOT NULL REFERENCES public.isd_briefings(run_date) ON DELETE CASCADE,
    content_hash text        NOT NULL,
    finding      jsonb       NOT NULL,
    status       text        NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'approved', 'rejected', 'merged')),
    resolved_by  text,
    resolved_at  timestamptz,
    UNIQUE (run_date, content_hash)            -- never queue the same finding twice
);

CREATE INDEX IF NOT EXISTS idx_isd_review_status ON public.isd_review_queue (status);

-- These are internal working tables, not public data. The two API roles get
-- nothing; the app writes with the owner connection. nlp_reader in particular
-- must never see them — it is the least-privilege role the LLM query path uses.
REVOKE ALL ON public.isd_briefings, public.isd_review_queue FROM anon, authenticated;
ALTER TABLE public.isd_briefings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.isd_review_queue ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlp_reader') THEN
        REVOKE ALL ON public.isd_briefings, public.isd_review_queue FROM nlp_reader;
    END IF;
END
$$;

-- Housekeeping, safe any time:
--   DELETE FROM public.isd_briefings WHERE run_date < current_date - 90;

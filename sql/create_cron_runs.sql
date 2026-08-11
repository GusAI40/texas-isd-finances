-- A record that a scheduled job ran, and what happened when it did.
--
-- Why this exists
-- ---------------
-- The daily intelligence cron failed silently for four days. Vercel fired it,
-- the handler raised, the handler swallowed it, and nothing anywhere recorded
-- that a run had been attempted. The only symptom was a briefing that quietly
-- stopped changing, which is indistinguishable from a slow news week.
--
-- The failure mode is specific and worth naming: a job that never runs and a
-- job that runs and writes nothing look identical from the outside. Every other
-- check in this project reads the OUTPUT of the pipeline. Nothing recorded the
-- ATTEMPT. So a cron that stopped being scheduled at all — an expired secret, a
-- renamed path, a plan downgrade — would never surface, because there is no row
-- whose absence anyone would notice.
--
-- This table makes absence visible. A gap in it is a finding.
--
-- Deliberately not a general log table. It holds one row per firing, is written
-- once at the end of a run, and carries no request data, no IP, no user agent
-- and no identifiers of any kind — the site's published privacy promise applies
-- here as much as anywhere.

CREATE TABLE IF NOT EXISTS public.cron_runs (
    id          BIGSERIAL PRIMARY KEY,
    job         TEXT        NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms INTEGER     NOT NULL,
    -- 'ok' | 'skipped' | 'error'. 'skipped' is a real outcome, not a failure:
    -- the intel cron is idempotent by date and a second call the same day is
    -- correct behaviour. Conflating it with 'error' would train whoever reads
    -- this to ignore errors.
    status      TEXT        NOT NULL CHECK (status IN ('ok', 'skipped', 'error')),
    -- What the run actually produced. Zero rows with status 'ok' is the exact
    -- shape of the original silent failure, so it must be recordable.
    rows_written INTEGER    NOT NULL DEFAULT 0,
    -- Truncated at the application. Never a full traceback: these can contain
    -- connection strings.
    detail      TEXT
);

-- The only query anyone runs against this: the last N firings of one job,
-- newest first, to see whether it is still alive and still producing.
CREATE INDEX IF NOT EXISTS idx_cron_runs_job_time
    ON public.cron_runs (job, started_at DESC);

-- Keep it small. This is an operational breadcrumb trail, not history worth
-- preserving: a month is far more than anyone will ever look back.
-- Run periodically, or leave it — the table grows by one row a day.
--   DELETE FROM public.cron_runs WHERE started_at < NOW() - INTERVAL '90 days';

ALTER TABLE public.cron_runs ENABLE ROW LEVEL SECURITY;

-- Readable by anyone, like everything else here: whether a public
-- transparency site's pipeline is running is itself public information, and
-- there is nothing in these rows that is not.
DROP POLICY IF EXISTS cron_runs_read ON public.cron_runs;
CREATE POLICY cron_runs_read ON public.cron_runs FOR SELECT USING (true);

GRANT SELECT ON public.cron_runs TO anon, authenticated;

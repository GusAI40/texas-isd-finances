-- First-party analytics: how the site is used, and what people ask it.
--
-- Why first-party
-- ---------------
-- The obvious option was Vercel Web Analytics. Two things ruled it out. The
-- same-origin script path (/_vercel/insights/script.js) never reaches Vercel
-- here, because this project routes EVERY path into FastAPI — the request just
-- 404s in the app. The CDN alternative (va.vercel-scripts.com) would require
-- widening a deliberately strict CSP (script-src 'self') to admit a
-- third-party script on every page. On a site whose public promise is
-- "privacy first", adding a third-party tracker to read a visitor counter is
-- the wrong trade. Counting server-side costs one upsert and no scripts.
--
-- What is deliberately NOT stored
-- -------------------------------
-- No IP address. No full user-agent. No cookie, no session or visitor id, no
-- fingerprint, no full referrer URL (those carry query strings, which carry
-- personal data). Nothing here can be traced back to a person: site_visits is
-- a DAILY COUNTER, not an event log — there is no row per visit and no
-- timestamp finer than the date, so two visitors on the same day are
-- arithmetically indistinguishable.
--
-- Idempotent; safe to re-run.

-- ---------------------------------------------------------------------------
-- Page views, as daily aggregate counters.

CREATE TABLE IF NOT EXISTS public.site_visits (
    day           date    NOT NULL,
    path          text    NOT NULL,            -- page route only, never a query string
    device        text    NOT NULL,            -- 'mobile' | 'desktop' | 'other'
    referrer_host text    NOT NULL DEFAULT '', -- host only ('google.com'), '' = direct
    hits          integer NOT NULL DEFAULT 0,
    PRIMARY KEY (day, path, device, referrer_host)
);

COMMENT ON TABLE public.site_visits IS
    'Daily page-view counters. Aggregate by construction: no per-visit row, no '
    'IP, no user-agent, no cookie or visitor id, and referrers are reduced to a '
    'host. A person cannot be identified from this table.';

-- ---------------------------------------------------------------------------
-- The questions people ask the "Ask anything" box.
--
-- This is the one place free text a visitor typed is retained, because knowing
-- what Texans want to know about their schools is what should shape the site.
-- It stores the QUESTION and nothing about who asked it — no IP, no session,
-- nothing that links two questions to the same person. The site's privacy note
-- says so in plain English; keep them in step.

CREATE TABLE IF NOT EXISTS public.nlp_questions (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asked_at timestamptz NOT NULL DEFAULT now(),
    question text        NOT NULL,             -- truncated by the app
    ok       boolean     NOT NULL DEFAULT true,-- did it answer, or error out
    ms       integer                           -- how long it took
);

COMMENT ON TABLE public.nlp_questions IS
    'What visitors asked the NLP endpoint. Question text only — no IP, no '
    'user-agent, no session or visitor id, so questions cannot be linked to a '
    'person or to each other.';

CREATE INDEX IF NOT EXISTS idx_nlp_questions_asked ON public.nlp_questions (asked_at DESC);

-- ---------------------------------------------------------------------------
-- Internal tables, not public data. Same lockdown as the rest: the two API
-- roles get nothing, RLS with no policy denies anything that slips past a
-- missing grant, and the app writes with the owner connection (which is not
-- subject to RLS). nlp_reader especially must never read nlp_questions — it is
-- the role the language model itself runs as.
REVOKE ALL ON public.site_visits, public.nlp_questions FROM anon, authenticated;
ALTER TABLE public.site_visits   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nlp_questions ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlp_reader') THEN
        REVOKE ALL ON public.site_visits, public.nlp_questions FROM nlp_reader;
    END IF;
END
$$;

-- Housekeeping, safe any time:
--   DELETE FROM public.nlp_questions WHERE asked_at < now() - interval '1 year';
--   DELETE FROM public.site_visits   WHERE day < current_date - 730;

-- Per-recipient journey tracking for outreach campaigns.
--
-- WHAT THIS IS, PLAINLY
-- ---------------------
-- Everything else in this project counts the SITE and never the visitor.
-- This file does the opposite, for one bounded population: people who were
-- sent a commercial email and chose to click the link in it. For those
-- people we record an identified event stream — opened, clicked, which pages,
-- how long, whether they came back.
--
-- That is a real change in posture, so it is fenced in code, not just in
-- intent:
--
--   * Tracking begins ONLY when someone arrives carrying a ?rid= token that
--     we minted and mailed to them. There is no fingerprinting, no
--     IP-matching, and no way for an anonymous visitor to fall into it.
--   * Anonymous visitors keep the old guarantee exactly: they are counted in
--     site_visits as daily totals and never appear in this table.
--   * The identity map (rid -> email) lives in its own table so it can be
--     dropped independently, and so a query over behaviour does not have to
--     join to a person unless it means to.
--   * Every row carries the campaign it came from, so a recipient's stream
--     can be deleted wholesale on request.
--
-- THE DISCLOSURE IS PART OF THIS FEATURE. The public privacy note must say
-- that email recipients who click through are measured individually. Shipping
-- the table without shipping the sentence is the failure mode this comment
-- exists to prevent.
--
-- Idempotent; safe to re-run.

-- ---------------------------------------------------------------------------
-- The identity map. One row per (recipient, campaign).

CREATE TABLE IF NOT EXISTS public.outreach_recipient (
    rid             text PRIMARY KEY,          -- opaque token, mailed in the link
    email           text        NOT NULL,
    district_number text        NOT NULL,
    campaign        text        NOT NULL DEFAULT 'w1',
    message_id      text,                      -- Resend id, ties back to the send
    sent_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outreach_recipient_email_idx
    ON public.outreach_recipient (email);
CREATE INDEX IF NOT EXISTS outreach_recipient_campaign_idx
    ON public.outreach_recipient (campaign);

COMMENT ON TABLE public.outreach_recipient IS
    'Maps an opaque per-email token to the person it was mailed to. This is '
    'the ONLY place a rid becomes a name. Drop this table and every behaviour '
    'row below becomes anonymous.';

-- ---------------------------------------------------------------------------
-- The event stream. One row per thing that happened.

CREATE TABLE IF NOT EXISTS public.visitor_event (
    id              bigserial PRIMARY KEY,
    rid             text        NOT NULL
                        REFERENCES public.outreach_recipient(rid)
                        ON DELETE CASCADE,
    visitor_id      text        NOT NULL,      -- first-party cookie; survives sessions
    session_id      text        NOT NULL,      -- one browsing sitting
    event           text        NOT NULL,      -- see CHECK below
    path            text,                      -- page route, e.g. '/forensics'
    district_number text,                      -- which district's report they viewed
    dwell_ms        integer,                   -- time on page, for 'dwell' events
    referrer_host   text        NOT NULL DEFAULT '',
    device          text        NOT NULL DEFAULT '',
    user_agent      text,
    ip              inet,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT visitor_event_kind CHECK (event IN
        ('email_open', 'click', 'pageview', 'dwell', 'question', 'return'))
);

CREATE INDEX IF NOT EXISTS visitor_event_rid_time_idx
    ON public.visitor_event (rid, occurred_at);
CREATE INDEX IF NOT EXISTS visitor_event_visitor_idx
    ON public.visitor_event (visitor_id, occurred_at);
CREATE INDEX IF NOT EXISTS visitor_event_time_idx
    ON public.visitor_event (occurred_at DESC);

COMMENT ON TABLE public.visitor_event IS
    'Identified behaviour stream for outreach recipients who clicked through. '
    'Populated ONLY for visitors carrying a minted ?rid= token. Anonymous '
    'visitors are never written here.';

-- ---------------------------------------------------------------------------
-- Roll-up: one row per recipient, the whole funnel at a glance.

CREATE OR REPLACE VIEW public.v_recipient_journey AS
SELECT
    r.rid,
    r.email,
    r.district_number,
    r.campaign,
    r.sent_at,
    min(e.occurred_at) FILTER (WHERE e.event = 'email_open')  AS first_open_at,
    count(*)           FILTER (WHERE e.event = 'email_open')  AS opens,
    min(e.occurred_at) FILTER (WHERE e.event = 'click')       AS first_click_at,
    count(*)           FILTER (WHERE e.event = 'pageview')    AS pageviews,
    -- A session only counts if a browser RENDERED something: a whitelist,
    -- because every server-side kind fabricates session ids — the pixel
    -- mints one per fetch, the reply ingest writes 'reply-<message_id>',
    -- and a cookieless scanner detonating the tracked link twice mints two
    -- "visits" without loading a page. Mirrors intel.BROWSER_SESSION_EVENTS
    -- (test-pinned). ensure_schema() re-applies this view on existing
    -- databases when the deployed definition is stale — the sentinel
    -- fast-path alone would never re-run it.
    count(DISTINCT e.session_id) FILTER (WHERE e.event IN
        ('pageview', 'dwell', 'section', 'return',
         'question', 'followup', 'download'))                 AS sessions,
    count(DISTINCT e.path) FILTER (WHERE e.event = 'pageview') AS distinct_pages,
    coalesce(sum(e.dwell_ms) FILTER (WHERE e.event = 'dwell'), 0) AS total_dwell_ms,
    max(e.occurred_at)                                        AS last_seen_at
FROM public.outreach_recipient r
LEFT JOIN public.visitor_event e ON e.rid = r.rid
GROUP BY r.rid, r.email, r.district_number, r.campaign, r.sent_at;

COMMENT ON VIEW public.v_recipient_journey IS
    'Funnel per recipient: sent -> opened -> clicked -> pages, dwell, return '
    'sessions. The reporting surface; prefer it over raw visitor_event.';

-- ---------------------------------------------------------------------------
-- Locked down: these tables are readable only by the service role. The NLP
-- reader (nlp_reader) must never see them — it answers public questions from
-- public data, and a prompt injection that reached this table would leak the
-- reading habits of named public officials.

ALTER TABLE public.outreach_recipient ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visitor_event      ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.outreach_recipient FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.visitor_event      FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.v_recipient_journey FROM PUBLIC, anon, authenticated;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlp_reader') THEN
        EXECUTE 'REVOKE ALL ON public.outreach_recipient FROM nlp_reader';
        EXECUTE 'REVOKE ALL ON public.visitor_event FROM nlp_reader';
        EXECUTE 'REVOKE ALL ON public.v_recipient_journey FROM nlp_reader';
    END IF;
END $$;

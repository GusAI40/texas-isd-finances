-- The intelligence layer: section engagement, chat conversations, experiments.
--
-- APPLIED AUTOMATICALLY by src/migrations.py on startup. This file is the
-- readable mirror; tests/test_migrations.py fails the build if the two ever
-- create different objects. `sql/` is excluded from the Vercel bundle, so the
-- copy that actually runs in production is the one in Python.
--
-- WHO IS IN HERE, AND WHO IS NOT
-- -----------------------------
-- The site's published promise is that it measures the site and not the
-- visitor, with ONE stated exception: people we emailed directly. Everything
-- below keeps that promise. Not one row is written for an anonymous visitor:
-- every write path requires the httpOnly `txj` cookie, which only exists for
-- someone who arrived on a ?rid= token we minted and mailed. Anonymous
-- visitors remain what they have always been — a number in site_visits.
--
-- WHY THE CONTENT AND THE IDENTITY LIVE IN DIFFERENT TABLES
-- --------------------------------------------------------
-- `chat_turn` holds what was asked and what we answered, keyed only by an
-- opaque conversation_id. `visitor_event` holds "this recipient asked a
-- question in that conversation". Joining them gives the named journey the
-- dashboard needs; `chat_turn` on its own is anonymous. That is the same
-- shape as outreach_recipient/visitor_event, where dropping one table makes
-- the other anonymous, and it is deliberate rather than incidental.

-- ---------------------------------------------------------------------------
-- 1. Widen the one event stream instead of starting a second one.
-- ---------------------------------------------------------------------------
-- Additive columns only. A separate "analytics events" table would be a second
-- source of truth for the same journey, and the first question anyone asked of
-- it would be which one to believe.

ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS section         text;
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS detail          text;
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS conversation_id text;
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS event_key       text;

COMMENT ON COLUMN public.visitor_event.section IS
    'Which part of the page, for section events. Slug from a data-section attribute.';
COMMENT ON COLUMN public.visitor_event.detail IS
    'One short label whose meaning depends on the event: the question topic, '
    'the download name, the follow-up chip clicked. Never free user text.';
COMMENT ON COLUMN public.visitor_event.event_key IS
    'Client-supplied idempotency key. sendBeacon retries and a page restored '
    'from bfcache both replay events; without this a 41-second read of the '
    'debt section could be counted three times and nothing would look wrong.';

-- Idempotency. Partial, so the millions of rows written before this existed
-- (and every server-side event, which cannot be replayed) stay unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS visitor_event_key_idx
    ON public.visitor_event (event_key) WHERE event_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS visitor_event_section_idx
    ON public.visitor_event (section, occurred_at) WHERE section IS NOT NULL;
CREATE INDEX IF NOT EXISTS visitor_event_conversation_idx
    ON public.visitor_event (conversation_id) WHERE conversation_id IS NOT NULL;

-- Widen the kind whitelist. This drops a CHECK and adds a strictly more
-- permissive one: no row is examined, no data is touched, and every value that
-- was legal before is legal after. Re-runnable because the drop is IF EXISTS.
ALTER TABLE public.visitor_event DROP CONSTRAINT IF EXISTS visitor_event_kind;
ALTER TABLE public.visitor_event ADD  CONSTRAINT visitor_event_kind CHECK (event IN (
    'email_open', 'click', 'pageview', 'dwell', 'question', 'return',
    'section', 'followup', 'download', 'reply'));

-- ---------------------------------------------------------------------------
-- 2. Conversations.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.chat_turn (
    id              bigserial PRIMARY KEY,
    conversation_id text        NOT NULL,
    turn            integer     NOT NULL,      -- 1, 2, 3 … within a conversation
    asked_at        timestamptz NOT NULL DEFAULT now(),
    question        text        NOT NULL,
    answer          text,                      -- null when the engine failed
    kind            text,                      -- src/answer.py classification
    district_number text,                      -- district in context, if any
    ok              boolean     NOT NULL DEFAULT true,
    ms              integer,                   -- end-to-end latency
    model           text,                      -- which provider actually served it
    structured      boolean     NOT NULL DEFAULT false,
    followup_label  text,                      -- the chip that produced it, if any
    error           text
);

CREATE INDEX IF NOT EXISTS chat_turn_conversation_idx
    ON public.chat_turn (conversation_id, turn);
CREATE INDEX IF NOT EXISTS chat_turn_time_idx  ON public.chat_turn (asked_at DESC);
CREATE INDEX IF NOT EXISTS chat_turn_kind_idx  ON public.chat_turn (kind, asked_at DESC);

COMMENT ON TABLE public.chat_turn IS
    'Every question and answer, in order, keyed by an opaque conversation id. '
    'Carries no identity of its own: the link to a person exists only in '
    'visitor_event, and only for recipients we emailed.';

-- ---------------------------------------------------------------------------
-- 3. Experiments (Phase 23) — the table exists so a change can be MEASURED
--    rather than argued about. Nothing writes to it until an experiment runs.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.experiment_exposure (
    id           bigserial PRIMARY KEY,
    experiment   text        NOT NULL,
    variant      text        NOT NULL,
    rid          text,                          -- null = anonymous, not attributed
    visitor_id   text,
    exposed_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (experiment, visitor_id)
);

CREATE INDEX IF NOT EXISTS experiment_exposure_exp_idx
    ON public.experiment_exposure (experiment, variant);

-- ---------------------------------------------------------------------------
-- 4. The reporting surface.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.v_conversation AS
SELECT
    t.conversation_id,
    count(*)                                  AS turns,
    min(t.asked_at)                           AS started_at,
    max(t.asked_at)                           AS last_at,
    count(*) FILTER (WHERE NOT t.ok)          AS failures,
    count(*) FILTER (WHERE t.followup_label IS NOT NULL) AS followups_used,
    round(avg(t.ms))                          AS avg_ms,
    max(t.district_number)                    AS district_number,
    array_agg(DISTINCT t.kind) FILTER (WHERE t.kind IS NOT NULL) AS kinds,
    max(e.rid)                                AS rid
FROM public.chat_turn t
LEFT JOIN public.visitor_event e
       ON e.conversation_id = t.conversation_id AND e.event = 'question'
GROUP BY t.conversation_id;

COMMENT ON VIEW public.v_conversation IS
    'One row per conversation. rid is non-null only when the asker arrived on '
    'a token we mailed; every other conversation stays anonymous.';

CREATE OR REPLACE VIEW public.v_section_engagement AS
SELECT
    e.section,
    e.district_number,
    count(DISTINCT e.rid)                          AS people,
    count(DISTINCT e.session_id)                   AS sessions,
    count(*)                                       AS views,
    coalesce(sum(e.dwell_ms), 0)                   AS total_dwell_ms,
    round(avg(e.dwell_ms))                         AS avg_dwell_ms
FROM public.visitor_event e
WHERE e.event = 'section' AND e.section IS NOT NULL
GROUP BY e.section, e.district_number;

COMMENT ON VIEW public.v_section_engagement IS
    'What people actually read inside a page. Recipients only — anonymous '
    'visitors emit no section events.';

ALTER TABLE public.chat_turn            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.experiment_exposure  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.chat_turn            FROM PUBLIC;
REVOKE ALL ON public.experiment_exposure  FROM PUBLIC;
REVOKE ALL ON public.v_conversation       FROM PUBLIC;
REVOKE ALL ON public.v_section_engagement FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    -- nlp_reader is the prompt-injection blast radius. It must never be able
    -- to read the questions other people asked, let alone who asked them.
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'REVOKE ALL ON public.chat_turn, public.experiment_exposure, '
                'public.v_conversation, public.v_section_engagement FROM %I', r);
        END IF;
    END LOOP;
END $$;

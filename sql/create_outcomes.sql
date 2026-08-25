-- Did any of this produce business?
--
-- Why this exists
-- ---------------
-- 671 emails have gone to named Texas superintendents. Every step of that is
-- instrumented: the queue, the send, the open pixel, the click, the pages read,
-- the dwell, the reply. And none of it answers the only question that matters,
-- which is whether a single conversation resulted.
--
-- A forensic audit on 2026-08-24 scored outcome measurement 1/5 — the lowest of
-- fifteen categories — because engagement is not an outcome. An open is a mail
-- scanner as often as a reader. A click proves a URL was fetched. Even a reply
-- only proves someone typed. None of them is a meeting, and none of them is
-- money. Completing an AI task is not itself a business result.
--
-- So this table records the thing the funnel was missing: what actually
-- happened afterwards, entered by a human who knows.
--
-- Deliberately NOT inferred
-- -------------------------
-- Nothing in this table is derived from behaviour. There is no rule that turns
-- three page views into a "warm lead" and no model that reads a reply and
-- decides it went well. Those inventions are how a funnel starts reporting
-- outcomes that never occurred — the same failure this project already refuses
-- in its data layers, where a masked cell is never a zero and an absence is
-- never a finding.
--
-- An outcome is here because a person recorded it. The absence of a row means
-- nobody knows, which is a true statement, and a far more useful one than a
-- confident guess.

CREATE TABLE IF NOT EXISTS public.outreach_outcome (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Who it concerns. district_number rather than email: the district is the
    -- durable party. A superintendent changes; the district does not, and an
    -- outcome recorded against a person who has left is an outcome nobody can
    -- find again.
    district_number text NOT NULL,

    -- Which attempt produced it, when that is known. Nullable on purpose: an
    -- outcome can arrive long after a wave, by a route nobody traced, and
    -- refusing to record it because the run_id is unknown would discard the
    -- exact information this table exists to hold.
    run_id          text,
    campaign        text,

    -- What happened. Ordered from weakest to strongest, so a report can ask
    -- "how far did this district get" rather than only "did it convert".
    --   replied            a human wrote back (not an auto-reply)
    --   conversation       a real exchange, more than one turn
    --   meeting_booked     a call or visit is on a calendar
    --   meeting_held       it actually happened
    --   scoped             we discussed specific work
    --   proposal_sent      a proposal exists
    --   engaged            they said yes
    --   declined           they said no — a real outcome, and the most common
    --   unsubscribed       they asked us to stop
    --   bounced            it never arrived
    kind            text NOT NULL CHECK (kind IN (
        'replied', 'conversation', 'meeting_booked', 'meeting_held',
        'scoped', 'proposal_sent', 'engaged', 'declined',
        'unsubscribed', 'bounced')),

    -- Money, only where money is real. NULL is the correct value for every
    -- outcome that has not been invoiced, and a projected or "pipeline" figure
    -- must never be entered here: a forecast in an outcome table becomes a
    -- reported result the moment somebody sums the column.
    value_usd       numeric(12, 2),

    -- Who says so, and what they are going on. `evidence` is a pointer — a
    -- thread subject, a calendar entry, an invoice number — not a narrative.
    noted_by        text NOT NULL,
    evidence        text,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    recorded_at     timestamptz NOT NULL DEFAULT now(),

    -- One district can reach the same milestone once. Recording "meeting_held"
    -- twice for one district double-counts the only number anyone will quote.
    -- A genuine second meeting is a second engagement, which belongs to a new
    -- campaign and therefore a different row.
    UNIQUE (district_number, kind, campaign)
);

CREATE INDEX IF NOT EXISTS outreach_outcome_district_idx
    ON public.outreach_outcome (district_number);
CREATE INDEX IF NOT EXISTS outreach_outcome_kind_idx
    ON public.outreach_outcome (kind, occurred_at DESC);

-- Same lockdown as every table holding named officials' behaviour. nlp_reader
-- especially: a prompt injection that reached the query role must not be able
-- to read who TAG ai is talking to.
ALTER TABLE public.outreach_outcome ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.outreach_outcome FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'REVOKE ALL ON public.outreach_outcome FROM %I', r);
        END IF;
    END LOOP;
END $$;

-- The run ledger: one row per outreach run, so a send can be traced from the
-- instruction that caused it to the outcome it produced.
--
-- cron_runs already records that a JOB fired. It cannot answer "which wave sent
-- this email", because a wave spans an enqueue (a human, with a token) and many
-- later drains (a cron, on a schedule). Nothing tied those together, so the
-- audit's question — who authorized this specific message — had no answer.
CREATE TABLE IF NOT EXISTS public.outreach_run (
    run_id        text PRIMARY KEY,
    campaign      text NOT NULL,
    started_at    timestamptz NOT NULL DEFAULT now(),
    -- 'enqueue' (a human staged a wave) or 'drain' (the cron sent a batch).
    kind          text NOT NULL CHECK (kind IN ('enqueue', 'drain')),
    -- How the run was authorized. Never a token value — the NAME of the gate
    -- that let it through, so an audit can say "a human with OUTREACH_TOKEN"
    -- or "the Vercel cron with CRON_SECRET" without storing either.
    authorized_by text NOT NULL,
    queued        integer NOT NULL DEFAULT 0,
    sent          integer NOT NULL DEFAULT 0,
    failed        integer NOT NULL DEFAULT 0,
    detail        text
);

CREATE INDEX IF NOT EXISTS outreach_run_campaign_idx
    ON public.outreach_run (campaign, started_at DESC);

ALTER TABLE public.outreach_run ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.outreach_run FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON public.outreach_run FROM %I', r);
        END IF;
    END LOOP;
END $$;

-- Link the queue to the run that created it. Additive and nullable: every row
-- already in the queue predates the ledger and must keep working.
ALTER TABLE public.outreach_queue
    ADD COLUMN IF NOT EXISTS run_id text;

-- Token telemetry. nlp_usage counted CALLS, which bounds the request rate and
-- says nothing about the bill: one question can cost twenty model calls in a
-- tool-calling loop, and a long context costs more than a short one at the same
-- call count. Additive and nullable so every existing row keeps working.
ALTER TABLE public.nlp_usage
    ADD COLUMN IF NOT EXISTS input_tokens  bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS output_tokens bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS model_calls   bigint NOT NULL DEFAULT 0;

-- The server-side outreach pipeline: the mailing list and the send queue,
-- living where the credentials live.
--
-- Why this exists (2026-08-19 root cause)
-- ---------------------------------------
-- Every send before this ran from a disposable dev container fed by keys
-- pasted into chat, reading a gitignored mailing-list CSV that existed only
-- on that container's disk. The container was reclaimed and the pipeline
-- died with it — not the data (Supabase and Resend kept everything), the
-- ACCESS. The deployed site is the one part of this system whose secrets
-- have survived every container loss, because Vercel stores them in platform
-- config. So the pipeline moves to the site: the mailing list becomes a
-- table, the wave becomes a queue, and the app's own pool (SUPABASE_DB_URL)
-- reads and writes all of it with no personal access token anywhere.
--
-- This file mirrors migrations.OUTREACH_DDL (the copy that actually runs,
-- self-applied on cold start); tests/test_outreach_runner.py fails the build
-- if the two describe different objects.
--
-- Lockdown: outreach_contact holds named public officials' addresses and
-- outreach_queue holds who is about to be mailed. Same treatment as
-- visitor_event — RLS on, zero grants, nlp_reader explicitly revoked so a
-- prompt injection that reached the NLP role cannot read a contact list.

-- outreach_sent / outreach_optout: born in sql/create_outreach_state.sql and
-- mirrored here because the runner reads and writes both — a fresh database
-- must work with no hand step. IF NOT EXISTS: a no-op where they exist.
CREATE TABLE IF NOT EXISTS public.outreach_sent (
    email           text PRIMARY KEY,
    district_number text,
    message_id      text,
    sent_at         timestamptz
);

CREATE TABLE IF NOT EXISTS public.outreach_optout (
    email    text PRIMARY KEY,
    noted_at timestamptz DEFAULT now()
);

ALTER TABLE public.outreach_sent   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outreach_optout ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.outreach_sent   FROM PUBLIC;
REVOKE ALL ON public.outreach_optout FROM PUBLIC;

CREATE TABLE IF NOT EXISTS public.outreach_contact (
    district_number text PRIMARY KEY,
    district_name   text NOT NULL,
    email           text NOT NULL,
    greeting        text NOT NULL DEFAULT 'Superintendent',
    subject         text NOT NULL,
    deep_link       text NOT NULL,
    hook            text NOT NULL DEFAULT '',
    insight_bonds   text NOT NULL DEFAULT '',
    insight_debt    text NOT NULL DEFAULT '',
    insight_trend   text NOT NULL DEFAULT '',
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outreach_contact_email_idx
    ON public.outreach_contact (email);

CREATE TABLE IF NOT EXISTS public.outreach_queue (
    id              bigserial PRIMARY KEY,
    district_number text        NOT NULL,
    email           text        NOT NULL UNIQUE,
    campaign        text        NOT NULL,
    status          text        NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'sending', 'sent', 'error')),
    detail          text,
    enqueued_at     timestamptz NOT NULL DEFAULT now(),
    claimed_at      timestamptz,
    sent_at         timestamptz
);

CREATE INDEX IF NOT EXISTS outreach_queue_status_idx
    ON public.outreach_queue (status, district_number);

ALTER TABLE public.outreach_contact ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outreach_queue   ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.outreach_contact FROM PUBLIC;
REVOKE ALL ON public.outreach_queue   FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'REVOKE ALL ON public.outreach_contact, '
                'public.outreach_queue, public.outreach_sent, '
                'public.outreach_optout FROM %I', r);
        END IF;
    END LOOP;
END $$;

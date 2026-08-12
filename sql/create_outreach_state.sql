-- Durable outreach state: who we emailed, who told us to stop.
--
-- Why this exists
-- ---------------
-- data/outreach_sent.csv and data/outreach_optout.txt are gitignored and
-- live only inside a disposable dev container. That is the wrong place for
-- this state: if the container is lost and the send is re-run, everyone gets
-- the email AGAIN — including people who unsubscribed. An opt-out is a
-- promise made to a named person; losing the file breaks the promise. A
-- duplicate send to everyone else is merely embarrassing, but re-emailing an
-- opt-out is the one failure this project must make impossible.
--
-- So the state lives here, in the same database that already outlives every
-- container. The local files remain (they work offline and are the write
-- path of record during a send); scripts/sync_outreach_state.py pushes them
-- up and can pull them back down, and scripts/send_outreach.py merges the
-- remote sets into its skip-lists before any real send and mirrors each
-- delivery up as it happens.
--
-- Idempotent — safe to re-apply. Writes go through the Management API
-- (service key), so no grants to anon/authenticated and RLS stays on with
-- no policies: the API roles can neither read nor write these rows.

CREATE TABLE IF NOT EXISTS public.outreach_sent (
    email           text PRIMARY KEY,
    district_number text,
    message_id      text,
    sent_at         timestamptz
);

COMMENT ON TABLE public.outreach_sent IS
    'One row per outreach email actually delivered (mirror of '
    'data/outreach_sent.csv). Durable so a lost container + re-run cannot '
    'double-email a superintendent.';

CREATE TABLE IF NOT EXISTS public.outreach_optout (
    email    text PRIMARY KEY,
    noted_at timestamptz DEFAULT now()
);

COMMENT ON TABLE public.outreach_optout IS
    'One row per address that asked us to stop (mirror of '
    'data/outreach_optout.txt). An opt-out is a promise; this table is the '
    'durable memory of it.';

-- No policies on purpose: only the Management API / service role touches
-- these. PostgREST roles get nothing.
ALTER TABLE public.outreach_sent   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outreach_optout ENABLE ROW LEVEL SECURITY;

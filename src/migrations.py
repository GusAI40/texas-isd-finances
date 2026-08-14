"""Schema the application creates for itself, once, if it is missing.

Why this exists
---------------
The journey-tracking tables were written as `sql/create_visitor_tracking.sql`
and then had to be applied by a human pasting them into a dashboard. That is a
bad place for a required step to live: it is easy to believe you did it when
you did not (the Supabase editor prints the same "Success. No rows returned"
for a migration that worked and a SELECT that found nothing), and until it is
done every click is dropped silently because `visitor_event.rid` is a foreign
key to a table that does not exist.

The application already holds a database credential with DDL rights. So it
applies this itself on startup and the manual step disappears.

Scope, deliberately narrow
--------------------------
This is NOT a migration framework and must not become one. It creates additive,
self-contained objects that nothing else depends on. It never drops, never
alters an existing column, and never touches the PEIMS finance tables — losing
a click is a nuisance, losing the district data is not recoverable from here.
Anything destructive stays a human decision with a backup taken first.

Cost on a cold start is one `to_regclass` lookup, which returns immediately
once the tables exist. The DDL runs at most once per database.

`sql/` is excluded from the Vercel bundle (see .vercelignore), so the statements
have to live here in deployed code rather than being read from the .sql file.
`tests/test_migrations.py` fails the build if the two ever describe different
objects.
"""
from __future__ import annotations

# The object whose absence means the whole migration has not run. Checked on
# every startup; cheap, and the answer is almost always "present".
SENTINEL = "public.visitor_event"

# Kept byte-comparable in intent with sql/create_visitor_tracking.sql — see the
# drift test. Every statement is idempotent, so two workers racing on a cold
# start cannot corrupt anything.
VISITOR_TRACKING_DDL = """
CREATE TABLE IF NOT EXISTS public.outreach_recipient (
    rid             text PRIMARY KEY,
    email           text        NOT NULL,
    district_number text        NOT NULL,
    campaign        text        NOT NULL DEFAULT 'w1',
    message_id      text,
    sent_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outreach_recipient_email_idx
    ON public.outreach_recipient (email);
CREATE INDEX IF NOT EXISTS outreach_recipient_campaign_idx
    ON public.outreach_recipient (campaign);

CREATE TABLE IF NOT EXISTS public.visitor_event (
    id              bigserial PRIMARY KEY,
    rid             text        NOT NULL
                        REFERENCES public.outreach_recipient(rid)
                        ON DELETE CASCADE,
    visitor_id      text        NOT NULL,
    session_id      text        NOT NULL,
    event           text        NOT NULL,
    path            text,
    district_number text,
    dwell_ms        integer,
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

CREATE OR REPLACE VIEW public.v_recipient_journey AS
SELECT
    r.rid, r.email, r.district_number, r.campaign, r.sent_at,
    min(e.occurred_at) FILTER (WHERE e.event = 'email_open')  AS first_open_at,
    count(*)           FILTER (WHERE e.event = 'email_open')  AS opens,
    min(e.occurred_at) FILTER (WHERE e.event = 'click')       AS first_click_at,
    count(*)           FILTER (WHERE e.event = 'pageview')    AS pageviews,
    count(DISTINCT e.session_id)                              AS sessions,
    count(DISTINCT e.path) FILTER (WHERE e.event = 'pageview') AS distinct_pages,
    coalesce(sum(e.dwell_ms) FILTER (WHERE e.event = 'dwell'), 0) AS total_dwell_ms,
    max(e.occurred_at)                                        AS last_seen_at
FROM public.outreach_recipient r
LEFT JOIN public.visitor_event e ON e.rid = r.rid
GROUP BY r.rid, r.email, r.district_number, r.campaign, r.sent_at;

ALTER TABLE public.outreach_recipient ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visitor_event      ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.outreach_recipient  FROM PUBLIC;
REVOKE ALL ON public.visitor_event       FROM PUBLIC;
REVOKE ALL ON public.v_recipient_journey FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    -- anon/authenticated exist on Supabase and not on a bare Postgres; nlp_reader
    -- is the prompt-injection blast radius and must never see who read what.
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'REVOKE ALL ON public.outreach_recipient, public.visitor_event, '
                'public.v_recipient_journey FROM %I', r);
        END IF;
    END LOOP;
END $$;
"""


# `CREATE TABLE IF NOT EXISTS` is NOT race-safe: concurrent creators fail with a
# duplicate key on pg_type rather than one of them yielding. On a serverless
# deploy every cold start races every other, so six workers hitting an empty
# database produced one success and five errors in testing. An advisory lock
# serialises them. It is TRANSACTION-scoped on purpose — Supabase's pooler runs
# in transaction mode, where a session-level lock can be left holding a
# connection that has already been handed to someone else.
_LOCK_KEY = 0x7B15D_000A            # arbitrary, just has to be ours alone


async def ensure_schema(pool) -> str:
    """Create the tracking schema if it is missing. Returns what happened.

    Never raises. A database that refuses this still serves every page — the
    site works with no database at all by design, and losing click tracking is
    not a reason to fail a request. The outcome is logged either way, because a
    tracking system that silently is not recording is the failure mode this
    whole feature was built to avoid.
    """
    if pool is None:
        return "skipped: no database pool"
    try:
        async with pool.acquire() as conn:
            # Fast path, and the one taken on all but the very first boot: no
            # lock, no transaction, one index lookup.
            if await conn.fetchval("SELECT to_regclass($1)", SENTINEL) is not None:
                return "ok: tracking schema already present"

            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", _LOCK_KEY)
                # Re-check under the lock. Measured: this does NOT reliably
                # observe a peer's commit once this connection has already run
                # the fast-path query above, so it is an optimisation and
                # nothing depends on it. Correctness comes from the lock (which
                # serialises) plus the statements being idempotent (so running
                # the script again is a no-op). Worst case on first boot is
                # every worker running a harmless script in turn, once ever.
                if await conn.fetchval("SELECT to_regclass($1)", SENTINEL) is None:
                    await conn.execute(VISITOR_TRACKING_DDL)

            if await conn.fetchval("SELECT to_regclass($1)", SENTINEL) is None:
                return "ERROR: ran the DDL but the tables are still missing"
            # Deliberately reports STATE, not authorship. Several workers can
            # each run the script on a cold-start burst, and a log line saying
            # "created" on all of them would be a small lie in exactly the place
            # someone looks to find out what happened.
            return "ok: journey-tracking schema ensured"
    except Exception as exc:                              # noqa: BLE001
        # A lost race is not a failure. Only report an error if the schema is
        # genuinely absent afterwards — otherwise a harmless collision would
        # fill the logs with alarms on every deploy.
        try:
            async with pool.acquire() as conn:
                if await conn.fetchval("SELECT to_regclass($1)", SENTINEL) is not None:
                    return "ok: tracking schema present (raced another worker)"
        except Exception:                                 # noqa: BLE001
            pass
        return f"ERROR: could not apply tracking schema ({exc})"

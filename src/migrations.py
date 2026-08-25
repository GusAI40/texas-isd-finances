"""Application-owned schema and privacy controls refreshed at startup.

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
This is NOT a general migration framework and must not become one. It manages
self-contained tracking, intelligence, outreach, and cron-privacy objects. The
unattended path never drops tables, views, or columns and never mutates the
PEIMS finance data. It can replace application-owned views and constraints and
reapply access controls when a security definition changes. The bounded
data-changing exception is ``CRON_LOG_PRIVACY_DDL``: it clears legacy free-text
operational details that may contain credentials or recipient addresses, adds
a controlled-code constraint, and revokes anonymous access. Anything broader
or destructive stays a human decision with a backup taken first.

Every startup checks three table sentinels plus the journey-view and cron-log
privacy markers. Current databases take the fast path; missing or stale state
is repaired under a transaction-scoped advisory lock. The DDL/security refresh
is idempotent and may run again when definitions change or cold starts race.

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
    count(DISTINCT e.session_id) FILTER (WHERE e.event IN
        ('pageview', 'dwell', 'section', 'return',
         'question', 'followup', 'download'))                 AS sessions,
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

# The journey view alone, sliced out of the block above so the two can never
# drift. It exists because the view's BODY changed after the sentinel-gated
# DDL first ran (2026-08-19: sessions became a whitelist over
# browser-rendered events — see intel.BROWSER_SESSION_EVENTS), and a sentinel
# gate only answers "does the object exist", never "is it current" — the
# INTEL_SENTINEL lesson, in view form. ensure_schema() re-applies this, under
# the same advisory lock, on any database whose deployed view predates the
# fix. The slice ends at the statement's own terminator; if the view text
# ever grows an interior semicolon the truncation produces invalid SQL, so
# the boundary is asserted here at import rather than discovered in a failed
# cold-start refresh.
_VIEW_START = VISITOR_TRACKING_DDL.index("CREATE OR REPLACE VIEW")
_VIEW_SQL = VISITOR_TRACKING_DDL[
    _VIEW_START:VISITOR_TRACKING_DDL.index(";", _VIEW_START) + 1]
if not _VIEW_SQL.rstrip().endswith("r.sent_at;"):    # not assert: -O strips it
    raise RuntimeError(
        "JOURNEY_VIEW_DDL slice no longer captures the whole view statement — "
        "an interior semicolon crept into the view text")

# The lockdown rides along, because the refresh path can also RECREATE the
# view after a drop: CREATE OR REPLACE on an existing view preserves its
# privileges, but a fresh CREATE on Supabase inherits default grants to
# anon/authenticated — and the view reads its base tables with owner rights,
# bypassing their RLS. Re-running these on an existing view is a no-op.
JOURNEY_VIEW_DDL = _VIEW_SQL + """

REVOKE ALL ON public.v_recipient_journey FROM PUBLIC;
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'REVOKE ALL ON public.v_recipient_journey FROM %I', r);
        END IF;
    END LOOP;
END $$;
"""


async def _journey_view_current(conn) -> bool:
    """Is the deployed view the corrected definition?

    Views carry no version, so currency is read off the definition itself.
    The marker is 'followup': it appears in the corrected body's session
    whitelist (Postgres deparses the IN to `= ANY (ARRAY[...])`, keeping
    every member) and in NO earlier version of the view, whose only filters
    were email_open/click/pageview/dwell. The marker must stay a member of
    intel.BROWSER_SESSION_EVENTS or every cold start re-applies the view
    forever — pinned by test. If the view is missing or unreadable the
    answer is "not current", which routes to the idempotent re-apply.
    """
    try:
        body = await conn.fetchval(
            "SELECT pg_get_viewdef('public.v_recipient_journey'::regclass)")
    except Exception:  # noqa: BLE001 — absent view == stale view
        return False
    return bool(body) and "followup" in body


# The intelligence layer. Mirrors sql/create_intel.sql — same drift test.
#
# It WIDENS the existing event stream rather than starting a second one: a
# separate analytics-events table would be a second source of truth for the
# same journey, and the first question anyone asked of it would be which one to
# believe. Every write path still requires the httpOnly cookie that only an
# emailed recipient carries, so the published promise is unchanged.
INTEL_DDL = """
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS section         text;
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS detail          text;
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS conversation_id text;
ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS event_key       text;

CREATE UNIQUE INDEX IF NOT EXISTS visitor_event_key_idx
    ON public.visitor_event (event_key) WHERE event_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS visitor_event_section_idx
    ON public.visitor_event (section, occurred_at) WHERE section IS NOT NULL;
CREATE INDEX IF NOT EXISTS visitor_event_conversation_idx
    ON public.visitor_event (conversation_id) WHERE conversation_id IS NOT NULL;

ALTER TABLE public.visitor_event DROP CONSTRAINT IF EXISTS visitor_event_kind;
ALTER TABLE public.visitor_event ADD  CONSTRAINT visitor_event_kind CHECK (event IN (
    'email_open', 'click', 'pageview', 'dwell', 'question', 'return',
    'section', 'followup', 'download', 'reply'));

CREATE TABLE IF NOT EXISTS public.chat_turn (
    id              bigserial PRIMARY KEY,
    conversation_id text        NOT NULL,
    turn            integer     NOT NULL,
    asked_at        timestamptz NOT NULL DEFAULT now(),
    question        text        NOT NULL,
    answer          text,
    kind            text,
    district_number text,
    ok              boolean     NOT NULL DEFAULT true,
    ms              integer,
    model           text,
    structured      boolean     NOT NULL DEFAULT false,
    followup_label  text,
    error           text
);

CREATE INDEX IF NOT EXISTS chat_turn_conversation_idx
    ON public.chat_turn (conversation_id, turn);
CREATE INDEX IF NOT EXISTS chat_turn_time_idx ON public.chat_turn (asked_at DESC);
CREATE INDEX IF NOT EXISTS chat_turn_kind_idx ON public.chat_turn (kind, asked_at DESC);

CREATE TABLE IF NOT EXISTS public.experiment_exposure (
    id           bigserial PRIMARY KEY,
    experiment   text        NOT NULL,
    variant      text        NOT NULL,
    rid          text,
    visitor_id   text,
    exposed_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (experiment, visitor_id)
);

CREATE INDEX IF NOT EXISTS experiment_exposure_exp_idx
    ON public.experiment_exposure (experiment, variant);

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

ALTER TABLE public.chat_turn            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.experiment_exposure  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.chat_turn            FROM PUBLIC;
REVOKE ALL ON public.experiment_exposure  FROM PUBLIC;
REVOKE ALL ON public.v_conversation       FROM PUBLIC;
REVOKE ALL ON public.v_section_engagement FROM PUBLIC;

CREATE TABLE IF NOT EXISTS public.site_feedback (
    id              bigserial PRIMARY KEY,
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    message         text        NOT NULL,
    page            text,
    district_number text,
    contact         text,
    rid             text,
    helpful         boolean
);

CREATE INDEX IF NOT EXISTS site_feedback_time_idx
    ON public.site_feedback (submitted_at DESC);

ALTER TABLE public.site_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_feedback FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'REVOKE ALL ON public.chat_turn, public.experiment_exposure, '
                'public.site_feedback, '
                'public.v_conversation, public.v_section_engagement FROM %I', r);
        END IF;
    END LOOP;
END $$;
"""

# The object whose absence means the intelligence layer has not been applied.
# Moved from chat_turn when site_feedback was added: the sentinel has to be
# the object created LAST, or a database that already ran an earlier version
# takes the fast path forever and never gets the new table.
INTEL_SENTINEL = "public.site_feedback"

# The server-side outreach runner (src/outreach_runner.py). Root cause of the
# 2026-08-19 outage: the mailing list and send pipeline lived in disposable
# containers fed by keys pasted into chat, and died with the container. The
# durable home for the pipeline is the deployed site (Vercel holds its keys
# in platform config — the one credential store in this system that has
# survived every container loss), so the mailing list and the send queue live
# in the same database as everything else the site owns.
#
# outreach_contact IS contact data — named public officials' addresses plus
# the per-district message fields. Same lockdown as visitor_event: RLS on, no
# grants, nlp_reader explicitly revoked. Writes arrive via the Management API
# (scripts/sync_outreach_contacts.py) or the app's own DDL-capable pool.
#
# outreach_queue is the wave: enqueue states WHO (after every skip-list), the
# daily drain sends a batch and records each delivery in outreach_sent /
# outreach_recipient exactly as the laptop script did. UNIQUE(email) makes a
# double-enqueue structurally impossible, matching the one-touch doctrine —
# an address is queued at most once, ever.
OUTREACH_DDL = """
-- outreach_sent and outreach_optout were born in sql/create_outreach_state.sql,
-- hand-applied. The runner reads AND writes both, so a fresh database must
-- get them without a hand step — the whole doctrine of this module. Shapes
-- mirror that file exactly; IF NOT EXISTS makes this a no-op on production,
-- which already has them.
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
"""

# Created LAST in OUTREACH_DDL, for the same reason INTEL_SENTINEL moved to
# site_feedback: the sentinel must be the newest object or old databases take
# the fast path forever.
OUTREACH_SENTINEL = "public.outreach_queue"


# ``cron_runs`` predates the self-applying schema. It was deliberately public,
# but its free-text ``detail`` column was fed truncated exception strings.
# Truncation is not redaction: provider errors can echo recipient addresses and
# driver errors can echo connection URIs. This one-time, idempotent hardening
# clears legacy free text, constrains future values to controlled codes, and
# makes the application endpoint the only anonymous read path (where legacy
# rows are independently redacted). The named constraint is the migration
# marker checked on each cold start.
CRON_LOG_PRIVACY_CONSTRAINT = "cron_runs_public_detail_code"
CRON_LOG_PRIVACY_DDL = f"""
DO $cron_privacy$
DECLARE
    r text;
BEGIN
    IF to_regclass('public.cron_runs') IS NOT NULL THEN
        UPDATE public.cron_runs
           SET detail = NULL
         WHERE detail IS NOT NULL
           AND detail NOT IN
               ('already_ran_today', 'empty', 'failed',
                'not_persisted', 'unarmed');

        IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conrelid = 'public.cron_runs'::regclass
               AND conname = '{CRON_LOG_PRIVACY_CONSTRAINT}'
        ) THEN
            ALTER TABLE public.cron_runs
                ADD CONSTRAINT {CRON_LOG_PRIVACY_CONSTRAINT}
                CHECK (detail IS NULL OR detail IN
                    ('already_ran_today', 'empty', 'failed',
                     'not_persisted', 'unarmed'));
        END IF;

        EXECUTE 'REVOKE ALL ON public.cron_runs FROM PUBLIC';
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'nlp_reader'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('REVOKE ALL ON public.cron_runs FROM %I', r);
            END IF;
        END LOOP;
    END IF;
END
$cron_privacy$;
"""


async def _cron_log_privacy_current(conn) -> bool:
    """Whether an existing cron log has the privacy migration marker."""
    if await conn.fetchval(
            "SELECT to_regclass('public.cron_runs')") is None:
        return True
    return bool(await conn.fetchval(
        "SELECT EXISTS ("
        "SELECT 1 FROM pg_constraint "
        "WHERE conrelid = 'public.cron_runs'::regclass AND conname = $1)",
        CRON_LOG_PRIVACY_CONSTRAINT))


# `CREATE TABLE IF NOT EXISTS` is NOT race-safe: concurrent creators fail with a
# duplicate key on pg_type rather than one of them yielding. On a serverless
# deploy every cold start races every other, so six workers hitting an empty
# database produced one success and five errors in testing. An advisory lock
# serialises them. It is TRANSACTION-scoped on purpose — Supabase's pooler runs
# in transaction mode, where a session-level lock can be left holding a
# connection that has already been handed to someone else.
_LOCK_KEY = 0x7B15D_000A            # arbitrary, just has to be ours alone


# The governance layer: what a run was, who authorized it, and what business
# result followed. Mirrors sql/create_outcomes.sql; tests/test_governance.py
# fails the build if the two describe different objects.
#
# GOVERNANCE_SENTINEL is outreach_outcome and is created FIRST in this script,
# so it cannot be the sentinel — the same lesson INTEL_SENTINEL and
# OUTREACH_SENTINEL each learned. outreach_run is created last, so a database
# that died halfway through still reports the work as unfinished.
GOVERNANCE_DDL = """
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
"""

GOVERNANCE_SENTINEL = "public.outreach_run"


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
            # lock, no transaction, two index lookups. BOTH sentinels are
            # checked — a deploy that added the intelligence layer to a
            # database which already had the tracking tables would otherwise
            # take the fast path forever and never apply it.
            have_tracking = await conn.fetchval(
                "SELECT to_regclass($1)", SENTINEL) is not None
            have_intel = await conn.fetchval(
                "SELECT to_regclass($1)", INTEL_SENTINEL) is not None
            have_outreach = await conn.fetchval(
                "SELECT to_regclass($1)", OUTREACH_SENTINEL) is not None
            have_governance = await conn.fetchval(
                "SELECT to_regclass($1)", GOVERNANCE_SENTINEL) is not None
            if have_tracking and have_intel and have_outreach and have_governance:
                journey_current = await _journey_view_current(conn)
                cron_privacy_current = await _cron_log_privacy_current(conn)
                if journey_current and cron_privacy_current:
                    return "ok: tracking schema already present"
                # A durable object exists but predates one of the security
                # migrations. The lock stops cold-starting workers racing.
                async with conn.transaction():
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock($1)", _LOCK_KEY)
                    if not journey_current:
                        await conn.execute(JOURNEY_VIEW_DDL)
                    if not cron_privacy_current:
                        await conn.execute(CRON_LOG_PRIVACY_DDL)
                return "ok: refreshed durable schema security"

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
                # Always after the tracking block: INTEL_DDL alters
                # visitor_event, so it cannot run against a database that does
                # not have it yet.
                if await conn.fetchval(
                        "SELECT to_regclass($1)", INTEL_SENTINEL) is None:
                    await conn.execute(INTEL_DDL)
                if await conn.fetchval(
                        "SELECT to_regclass($1)", OUTREACH_SENTINEL) is None:
                    await conn.execute(OUTREACH_DDL)
                # After OUTREACH_DDL without exception: this script ALTERs
                # outreach_queue, so it cannot run against a database that does
                # not have it yet.
                if await conn.fetchval(
                        "SELECT to_regclass($1)", GOVERNANCE_SENTINEL) is None:
                    await conn.execute(GOVERNANCE_DDL)
                # The view refresh must ALSO run here, not only on the fast
                # path: a database with the tracking sentinel but not the
                # intel one takes this branch, skips VISITOR_TRACKING_DDL
                # (sentinel present), and would otherwise boot with the
                # stale view until some later cold start.
                if not await _journey_view_current(conn):
                    await conn.execute(JOURNEY_VIEW_DDL)
                if not await _cron_log_privacy_current(conn):
                    await conn.execute(CRON_LOG_PRIVACY_DDL)

            for name in (SENTINEL, INTEL_SENTINEL, OUTREACH_SENTINEL,
                         GOVERNANCE_SENTINEL):
                if await conn.fetchval("SELECT to_regclass($1)", name) is None:
                    return f"ERROR: ran the DDL but {name} is still missing"
            # Deliberately reports STATE, not authorship. Several workers can
            # each run the script on a cold-start burst, and a log line saying
            # "created" on all of them would be a small lie in exactly the place
            # someone looks to find out what happened.
            return "ok: journey-tracking schema ensured"
    except Exception as exc:                              # noqa: BLE001
        # A lost race is not a failure. Only report an error if the schema is
        # genuinely absent afterwards — otherwise a harmless collision would
        # fill the logs with alarms on every deploy. The view's currency is
        # part of that check: a failed view refresh (wrong owner, pooler
        # killed the DDL) used to land here, find both table sentinels, and
        # report "ok" on every cold start while the view stayed stale — a
        # failed migration looking identical to a working one, from the
        # module built to prevent exactly that.
        try:
            async with pool.acquire() as conn:
                sentinels_present = True
                for name in (SENTINEL, INTEL_SENTINEL, OUTREACH_SENTINEL,
                         GOVERNANCE_SENTINEL):
                    if await conn.fetchval(
                            "SELECT to_regclass($1)", name) is None:
                        sentinels_present = False
                        break
                if (sentinels_present
                        and await _journey_view_current(conn)
                        and await _cron_log_privacy_current(conn)):
                    return "ok: tracking schema present (raced another worker)"
        except Exception:                                 # noqa: BLE001
            pass
        # This string is exposed by /health. Driver error text can contain a
        # connection URI, so retain only the exception class.
        return ("ERROR: could not apply tracking schema "
                f"({type(exc).__name__}); detail redacted")

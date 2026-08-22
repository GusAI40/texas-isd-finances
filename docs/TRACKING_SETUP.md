# Turning on journey tracking

**Step 1 is now automatic.** On startup, `src/migrations.py` checks the tracking,
intelligence, and outreach sentinels, the current journey-view definition, and
the cron-log privacy marker. It creates missing application-owned objects and
refreshes stale view, constraint, or access-control state under an advisory
lock; no dashboard paste is part of the normal deploy path.

That leaves **only Step 2** for a human — and even that is recoverable if
missed. The manual instructions below are kept because they still work, and
because a self-applying migration is only as good as your ability to check it
by hand.

### How to confirm it applied

After the next deploy, either read the deployment logs for the line

```
schema: ok: journey-tracking schema ensured
schema: ok: tracking schema already present
schema: ok: refreshed durable schema security
schema: ok: tracking schema present (raced another worker)
```

Any one of those `ok:` states is successful. A line starting `schema: ERROR:`
means startup could not apply or verify the current state. The manual tracking
check below is useful evidence, but `/health` also checks the broader startup
result and must report `tracking_schema=ready`.

Why it reports state rather than "created": on a cold-start burst several
workers can each run the idempotent script, and a log saying "created" on all
of them would be untrue in exactly the place someone looks to find out what
happened.

⚠️ The unattended path never drops tables, views, or columns and never
mutates the finance data. More precisely,
`tests/test_migrations.py` prohibits `DROP TABLE`, `DROP VIEW`, `DROP COLUMN`,
`TRUNCATE`, `DELETE FROM`, and `ALTER COLUMN` in `VISITOR_TRACKING_DDL`; it does
not claim that every DDL string is append-only. The application can replace its
journey view and event constraint and reapply grants. The bounded cron-log
privacy repair updates unsafe legacy free text to `NULL`, constrains future
values to controlled codes, and revokes direct anonymous access. All of these
operations are idempotent and avoid the finance tables.

---

## Step 1 (manual recovery only) — Inspect or repair tracking objects

Do not assume these objects are absent: current deployments normally create and
verify them at startup. Use this path only to inspect the production project or
to repair the tracking/journey subset after an explicit startup error. Without
`outreach_recipient` and `visitor_event`, clicks are discarded because an event
has nowhere durable to point, while the rest of the portal keeps serving.

1. Open the SQL editor for the production project:
   **https://supabase.com/dashboard/project/zwhvabkvrexphlskubog/sql/new**
   (Sign in as the account that owns the `texas-isd-finances` project. If you
   land somewhere else, pick that project first, then **SQL Editor** in the
   left sidebar, then **New query**.)

2. From a verified checkout of current `master`, open
   `sql/create_visitor_tracking.sql`; or open the **raw** current file and
   select all / copy:
   **https://raw.githubusercontent.com/GusAI40/texas-isd-finances/master/sql/create_visitor_tracking.sql**
   (Use the raw view, not the pretty GitHub file view — it is plain text with
   nothing else on the page to copy by accident.)

3. Paste it into the SQL editor and press **Run** (or Ctrl/Cmd + Enter).

4. Expect `Success. No rows returned.` That is what success looks like for a
   migration — it creates things, it does not return things.

**It is safe to run twice.** The tracking SQL is idempotent. Re-running can
replace the journey view and reapply constraints or grants, so it may repair
state; it is not accurate to say that it always changes nothing. This file
covers the tracking/journey subset only. The application startup remains the
authority for intelligence, outreach, and cron-log privacy readiness.

### Check it worked

⚠️ Do not use a check that can return zero rows. `Success. No rows returned`
is *also* what the migration prints, and what a SELECT prints when it finds
nothing — so that message cannot tell you which happened. Use this instead,
which always returns exactly one row saying true or false:

```sql
SELECT
  to_regclass('public.outreach_recipient') IS NOT NULL AS recipient_table,
  to_regclass('public.visitor_event')      IS NOT NULL AS event_table,
  to_regclass('public.v_recipient_journey') IS NOT NULL AS journey_view;
```

Three `true` values means you are done. Any `false` means the migration has
not run yet — go back to step 3.

---

## Step 2 (local fallback only) — Use `SUPABASE_PAT` with the local sender

The current production server-side runner writes journey tokens through the
application's database pool; it does not need a Supabase Personal Access Token.
The instructions in this section apply only to the local fallback sender and
management scripts. With `SUPABASE_PAT`, that path mirrors each token to the
database. Without it, the local sender warns and keeps tokens only in
`data/outreach_recipients.csv`, requiring the recovery push below.

**Where to get one:** https://supabase.com/dashboard/account/tokens →
*Generate new token* → name it something like `outreach-send` → copy it. It
starts with `sbp_`. You only see it once.

**Never paste it into a chat.** Set it in the shell that runs the send:

```bash
export SUPABASE_PAT=sbp_...          # paste yours here
export RESEND_API_KEY=re_...
export TAG_POSTAL_ADDRESS="your physical address"

python scripts/send_outreach.py --send --confirm GO --limit 50 --campaign w2
```

### If a local fallback send omitted the PAT

A wave sent with no `SUPABASE_PAT` is not lost. The tokens are in
`data/outreach_recipients.csv`. Push them up:

```bash
SUPABASE_PAT=sbp_... python scripts/sync_outreach_state.py --push
```

This works for anyone who **has not clicked yet**. A click that arrives before
the token reaches the database is gone for good — so if you notice the warning,
run this the same day, not next week.

---

## Then what

```bash
SUPABASE_PAT=sbp_... python scripts/journey_report.py
SUPABASE_PAT=sbp_... python scripts/journey_report.py --email supt@somewhere-isd.net
```

The first prints the funnel (sent → opened → clicked → came back) and the most
engaged recipients. The second prints one person's full timeline, session by
session.

---

## What this does not cover

**Wave 1's 571 emails cannot be tracked.** Their links are already sitting in
inboxes without a token, and nothing can add one now. Tracking starts with the
next wave. Opens for wave 1 are still readable from Resend via
`scripts/outreach_kpi.py`.

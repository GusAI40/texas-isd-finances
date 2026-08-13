# Turning on journey tracking — the two manual steps

Everything else is code and already shipped. These two things need a human
with the account, once. Ten minutes, no command line required for step 1.

---

## Step 1 — Create the tables (no CLI, no token)

The database has no `outreach_recipient` / `visitor_event` tables yet. Until it
does, **every click is thrown away silently** — `visitor_event.rid` is a
foreign key to `outreach_recipient`, so an event with nowhere to point is
rejected. Nothing breaks; you just get no data.

1. Open the SQL editor for the production project:
   **https://supabase.com/dashboard/project/zwhvabkvrexphlskubog/sql/new**
   (Sign in as the account that owns the `texas-isd-finances` project. If you
   land somewhere else, pick that project first, then **SQL Editor** in the
   left sidebar, then **New query**.)

2. Open the **raw** migration text and select all / copy:
   **https://raw.githubusercontent.com/GusAI40/texas-isd-finances/claude/audit-public-launch-ocd7ra/sql/create_visitor_tracking.sql**
   (Use the raw view, not the pretty GitHub file view — it is plain text with
   nothing else on the page to copy by accident.)

3. Paste it into the SQL editor and press **Run** (or Ctrl/Cmd + Enter).

4. Expect `Success. No rows returned.` That is what success looks like for a
   migration — it creates things, it does not return things.

**It is safe to run twice.** Every statement is `IF NOT EXISTS` /
`CREATE OR REPLACE`; re-running changes nothing. If you are unsure whether it
worked, just run it again.

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

## Step 2 — Have `SUPABASE_PAT` set when you send

When the sender mails someone, it writes their journey token to the database.
It needs a **Supabase Personal Access Token** to do that. Without one it still
sends the email and still writes the token to `data/outreach_recipients.csv`
locally — it just cannot put it in the database, and warns on every recipient.

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

### If you forget — it is recoverable now

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

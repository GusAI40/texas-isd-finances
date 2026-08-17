---
name: outreach
description: The superintendent outreach machine for texas-isd-finances — how to safely prepare, send, verify, and account for email waves to Texas school superintendents, and how to read the results. Use this whenever the user asks to send outreach, send emails to superintendents, run the next wave, check outreach status/KPIs, sync outreach state, or asks anything about who has been emailed, opened, or clicked. Also use BEFORE touching any file matching data/outreach_* — every one of them is load-bearing send state, and this skill explains which mistakes re-email 571 real people.
---

# Outreach — sending email to real superintendents without breaking a promise

Every address in this system belongs to a named public official. A duplicate
send is spam to someone we asked to trust us; an email to an opted-out address
is a broken promise to a person. The machine has rails for both, but the rails
only hold if you understand where the state lives. Read this whole file before
running anything with `--send`.

## Where the state lives (the whole design in one table)

| Thing | Where | Survives container loss? |
|---|---|---|
| Sent log (who got mail) | `data/outreach_sent.csv` (gitignored) | NO — container only |
| Sent log mirror | Supabase `public.outreach_sent` | YES — IF pushed with `SUPABASE_PAT` |
| Opt-outs | `data/outreach_optout.txt` + Supabase mirror | file NO / mirror YES |
| Suppressions (bounces, provider blocks) | `data/outreach_suppression.json` | NO — container only |
| **Watermark (the floor)** | `data/outreach_watermark.json` (COMMITTED) | YES — it is the only send state in git |
| Mailing list | `data/outreach_merge.csv` (gitignored) | NO — rebuild with `scripts/build_outreach_merge.py` |
| Journey tokens (rid → person) | `data/outreach_recipients.csv` + Supabase `outreach_recipient` | file NO / mirror YES |

The trap this table exists to prevent: `_remote_emails()` returns an EMPTY
set when `SUPABASE_PAT` is unset — documented offline mode, not an error — so
a fresh container with no local log and no PAT resolves a skip-list of zero
and would re-email everyone. The committed watermark makes that impossible:
`send_outreach.py` refuses when the resolved skip-list is smaller than
`unique_emails` in the watermark, because a shrinking skip-list means state
was LOST, never that people un-received email. Never pass
`--ignore-watermark` unless the owner has said, in this conversation, that
they understand exactly which guarantee they are overriding.

## Credentials — and the one thing never to do

A real send needs three environment variables; the script refuses without the
first two:

- `RESEND_API_KEY` — the Resend account (sender `gus@ubntag.com`, domain
  verified in Resend).
- `TAG_POSTAL_ADDRESS` — CAN-SPAM requires a physical postal address in every
  commercial email. No address, no send, by law and by code.
- `SUPABASE_PAT` — unions the remote skip-list before sending, mirrors each
  delivery up as it happens, and pushes the journey tokens. A send without it
  works but produces a wave whose clicks can never be attributed to people
  (this happened once; it is recoverable only same-day via
  `sync_outreach_state.py`).

**Never ask for, or accept, credentials pasted into chat.** Seven credentials
pasted in past sessions are on the owner's rotate list; do not add an eighth.
If the variables are missing, stage everything (dry run, previews, state
verification), then tell the owner to add them to the environment settings at
code.claude.com and run the send from a session that has them.

## Pre-flight — run every step, in order, before any `--send`

1. **Environment**: confirm the three variables above. Report which are
   missing rather than improvising around them.
2. **State integrity**: count unique emails in `data/outreach_sent.csv` and
   compare to `unique_emails` in `data/outreach_watermark.json`. With
   `SUPABASE_PAT`, also verify `SELECT count(*) FROM public.outreach_sent`
   equals the watermark (use the Supabase Management API over HTTPS — direct
   Postgres is blocked from this container). If the REMOTE is short, run
   `python scripts/sync_outreach_state.py` (push) BEFORE anything else: the
   mirror is the only copy that outlives this container.
3. **Mailing list**: if `data/outreach_merge.csv` is missing (fresh
   container), rebuild it with `python scripts/build_outreach_merge.py`
   (AskTED contacts are public TEA data; expect ~1,019 rows). Spot-check that
   insights in a few rows name the ROW'S OWN district — the identity gate
   (`verify_targets()`) enforces this at send time, but a broken merge should
   be caught here, not there. Two rules learned 2026-08-17:
   - **The Socrata AskTED dataset (`hzek-udky`) is a stale mirror.** Check
     `rowsUpdatedAt` on `data.texas.gov/api/views/hzek-udky.json` before
     calling any pull "fresh" — on 2026-08-17 it was still the May 12
     snapshot, missing the entire summer superintendent-turnover season. The
     live directory is askted.tea.texas.gov (blocked from this container's
     network; its export needs a human download or another network). A
     "fresh pull" from a stale mirror is the freshness-check-watching-the-
     wrong-page failure all over again.
   - **After any roster refresh, dedupe by DISTRICT, not only email.** The
     skip-list keys on addresses; a district whose superintendent changed
     gets a NEW address and would sail past it — re-mailing a district that
     was already contacted, just to a different person. The sent log carries
     `district_number`: exclude those districts from the wave unless the
     owner explicitly wants to re-introduce to new superintendents.
4. **Dry run** — costs nothing, sends nothing, and is the real review:
   ```bash
   python scripts/send_outreach.py --limit <N> --campaign wave<K>-<YYYY-MM-DD> --previews 3
   ```
   Read at least one preview in `data/outreach_preview/` end to end. Confirm
   the target count is exactly N after the skip-list and suppression list are
   applied, and report the first and last district so the owner can see the
   selection is deterministic.
5. **Optional real-inbox check**: `--test <owner's email>` sends two real
   messages to the owner only.

## The send

```bash
python scripts/send_outreach.py --send --confirm GO --limit <N> --campaign wave<K>-<YYYY-MM-DD>
```

- `--campaign` is not decoration: it labels every journey token, so one
  wave's behaviour can be reported — or deleted — alone. Always set it.
- The rails that fire automatically: `--confirm GO` required; Resend domain
  verified via the API before message one; every delivery appended to the
  sent log immediately (a crash halfway cannot double-email); opt-outs
  honoured with a List-Unsubscribe header; `verify_targets()` refuses any row
  whose deep link, site name, or insights are not the row's own district.
- Watch the output to the end. A mirror-push failure warns loudly but does
  not abort — if you see that warning, the same-day recovery is
  `python scripts/sync_outreach_state.py` (push) as soon as the send ends.

## Post-send bookkeeping — the send is not done when the emails leave

1. **Mirror the state up**: `python scripts/sync_outreach_state.py` (push),
   then verify the remote count equals local. This is the step that makes the
   wave survive the container.
2. **Bump the watermark in the same commit** as anything else the wave
   touches: `sent_total`, `unique_emails`, and append the wave to `waves[]`
   in `data/outreach_watermark.json`. The guard compares against
   `unique_emails` (addresses, not sends — two districts can share one
   address). Master is branch-protected, so this lands via a PR like
   everything else.
3. **Log it** (`/ariba save`): date, count, campaign label, anything that
   fired a rail. The log is the only memory the next session has.
4. **Report to the owner**: sent count, campaign label, and the standing
   caveats that apply (see below) — not just "done".

## Reading the results

- `python scripts/outreach_kpi.py` — pulls each message's last event from
  Resend into `data/outreach_kpi_report.csv` and upserts `outreach_status`
  (needs `RESEND_API_KEY`; add `SUPABASE_PAT` to persist).
- `python scripts/journey_report.py` — per-recipient journeys (opens via our
  own pixel, pages, dwell, returns) for TRACKED waves only.
- Campaign-level click-through is also counted first-party as `src:email` in
  `site_visits` — no Resend needed.

<<<<<<< HEAD
**The biggest one: telling a superintendent from a mail-security appliance.**
Districts run Defender / Barracuda / Mimecast, which open every message and
follow every link within seconds. In the raw counters they are
indistinguishable from eager readers.

**Use the signal that actually discriminates: JavaScript execution.** `click`
and `pageview` are written SERVER-SIDE by the HTTP request, so a scanner
fetching the URL produces both and proves nothing. `dwell` only exists if
`static/track.js` ran in a real rendering engine with the tab VISIBLE for a
second or more. `journey_report.py` classifies on this and prints three
grades — confirmed human / ambiguous browser farm / machine only — plus an
honest RANGE. Quote the range.

**The mistake worth not repeating:** the first version of this filter rejected
any click within 120 seconds of send, reasoning that fast clicks are machines.
It discarded seven recipients who had demonstrably rendered the page, and
turned a raw 17% into a published 8% — further from the truth (11–15%) than
the raw number was. **Latency is evidence about machines, never about
humans**; plenty of people read mail the moment it arrives. An over-aggressive
filter is as wrong as no filter and more dangerous, because it feels rigorous.

**Fan-out is the remaining tell.** One recipient producing clicks from 13–15
distinct user agents across many sessions over hours is an appliance farm
(some detonate links in real headless browsers, so they DO produce dwell).
Above `MAX_HUMAN_USER_AGENTS` a recipient is ambiguous — a reader may be
inside — so it is neither counted nor discarded.

**Never quote an open rate.** The pixel is fired by scanners that showed
nobody the message and blocked by clients that suppress images. It is wrong in
both directions with no way to bound the error. Wave 2's raw pixel says 49%;
the number is unusable, not merely uncertain.

**Dwell time is capped by the instrument**: `track.js` flushes every 60s, so
"1m 00s" means "at least a minute, still open", not a measured duration.
=======
**The biggest one: raw opens and clicks are mostly machines.** School districts
run mail-security appliances (Microsoft Defender, Barracuda, Mimecast) that
open every message and follow every link within seconds of delivery, to check
them. In the raw counters they are indistinguishable from eager readers. On
wave 2 (2026-08-17) this was **6 of 14 "clicks" and roughly three quarters of
the "opens"**. `journey_report.py` now prints raw AND verified counts; quote
the **verified click** figure and nothing else as engagement. The two
signatures, both confirmed against real data:

- **Time.** No human opens mail one second after it is sent. Anything within
  120s of that recipient's OWN send is a machine. (Hardin ISD "clicked" at
  +1s; 21 opens fired inside 30s.)
- **Dead clients.** Windows XP, IE 8, and AppEngine fetchers in 2026 are
  appliances in costume — 32 recipients produced events from these.
- **Bonus tell:** one recipient generating clicks from *five different
  browsers at once* is an appliance fanning out, not a diligent reader.

Opens are unreliable in BOTH directions — scanners inflate them, image
blocking deflates them — so a range is the honest form, never a point
estimate. Also note **dwell time is capped by the instrument**: `track.js`
flushes every 60s, so "1m 00s" means "at least a minute, still open", not a
measured duration.
>>>>>>> origin/master

Interpretation rules that have already prevented false findings once:
- **Wave 1 (the 571 sent 2026-08-11/12/13) is untracked forever** — its links
  are delivered and cannot be retrofitted. Its `clicked` will read zero for
  all time; that is an instrument fact, not reader behaviour.
- Resend's own click tracking was a disabled toggle during wave 1 — 0 clicks
  there is the toggle, not a verdict. Our first-party tracking does not
  depend on it.
- The 08-11 batch shows zero OPENS for the same reason (tracking predated the
  `gus@ubntag.com` default). Never compare batches across an instrument
  change without saying so.

## Gotchas with scars behind them

- **Cloudflare 403 from Resend or Supabase APIs is a missing User-Agent
  header, not an auth failure.** Send a UA (the scripts do) or use curl.
- The open pixel (`/px/{rid}.gif`) renders inside a superintendent's inbox —
  it must never 500. Tracking paths read the DB pool via `_pool_or_none()`.
- Vercel is on Hobby (non-commercial terms) — flag the Pro upgrade whenever a
  wave is discussed; these emails introduce TAG ai.
- `gus@ubntag.com` is the only monitored mailbox; replies land there.
- The two bond-vendor companion CSVs must never be ingested (they carry a
  CRM with named reps and commissions). Not outreach files, but they live in
  the same neighbourhood — listed here because "while I'm in data/" is how it
  would happen.
- Outreach CSVs are deliberately excluded from the public raw-data archive:
  they are private contact data, not state records.

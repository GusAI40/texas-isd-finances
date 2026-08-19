"""The outreach machine, running where the keys live.

Root cause this closes (2026-08-19): every send before this ran from a
disposable container fed by credentials pasted into chat, reading a mailing
list that existed only on that container's disk. The container died and the
pipeline died with it — the data survived (Supabase, Resend), the access did
not. The deployed site is the one component whose secrets have survived every
container loss, so the pipeline moves here: selection reads the
`outreach_contact` table, the wave is a row-per-recipient `outreach_queue`,
and every delivery lands in `outreach_sent` / `outreach_recipient` through
the app's own pool — no personal access token, no local files, no container.

Two operations, deliberately separated:

  ENQUEUE — states the wave. Applies every rail the laptop script applied:
    the skip-list (nobody in `outreach_sent` is ever queued), opt-outs, the
    committed suppression hashes, the committed watermark floor, and the
    identity gate (every row must deep-link to its own district and name it
    in every sentence). Requires the admin token AND the literal word GO.
    Enqueuing sends nothing.

  DRAIN — sends one small batch from the queue, throttled to Resend's rate,
    inside one serverless invocation's budget. Fired by Vercel Cron daily and
    by hand ("kick") as often as wanted; two drains racing claim disjoint
    rows. Each message is logged the moment Resend accepts it, so a crash
    mid-batch cannot double-send: the skip is the log.

The rails hold structurally, not procedurally: UNIQUE(email) on the queue
makes double-enqueue impossible, the sent-log insert is ON CONFLICT DO
NOTHING, and a row that fails after claiming stays visible as 'sending' for a
human to look at rather than being silently retried into a duplicate.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from functools import lru_cache
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from . import outreach_email, tracking

ROOT = Path(__file__).resolve().parent.parent
WATERMARK = ROOT / "data" / "outreach_watermark.json"
SUPPRESSION = ROOT / "data" / "outreach_suppression.json"
FALLBACK_INDEX = ROOT / "static" / "fallback_index.json"

# One invocation's sending budget. Resend's public limit is 2/s; 1.1s spacing
# matches the laptop script, and 15 messages ≈ 17s stays inside even a
# conservative serverless duration cap with render/log overhead.
BATCH = 15
THROTTLE_S = 1.1
# Stop claiming-new-work at this wall-clock point and release what is left:
# the function's own maxDuration (vercel.json) is 60s, and rows released
# before any attempt cost nothing while rows stranded past the platform kill
# would be quarantined unsent. The budget plus the WORST CASE of one
# in-flight Resend call (RESEND_TIMEOUT_S below, passed to resend_request —
# the laptop default of 30s would blow straight through the cap) must stay
# under maxDuration with room for the final bookkeeping: 40 + 15 = 55 < 60.
WALL_BUDGET_S = 40
RESEND_TIMEOUT_S = 15
# A 'sending' row older than this with no matching sent-log entry means a
# drain died mid-message. It is REPORTED, never auto-retried: the message may
# or may not have left, and a duplicate email to a named official costs more
# than a missing one.
STALE_SENDING_S = 3600


def _digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def suppressed_digests() -> set[str]:
    """Committed SHA-256 hashes of addresses that must never be mailed."""
    if not SUPPRESSION.exists():
        return set()
    return set(json.loads(SUPPRESSION.read_text()).get("entries", {}))


def watermark_floor() -> int:
    """How many addresses the committed record says have been emailed."""
    if not WATERMARK.exists():
        return 0
    d = json.loads(WATERMARK.read_text())
    return int(d.get("unique_emails", d.get("sent_total", 0)))


@lru_cache(maxsize=1)
def _site_names() -> dict[str, str]:
    """district_number -> name from the committed fallback index. Cached: the
    file is immutable per deploy, and the drain calls the identity gate once
    per message — re-parsing 82KB of JSON on the event loop each time buys
    nothing."""
    try:
        fb = json.loads(FALLBACK_INDEX.read_text())
        return {d["district_number"]: d["district_name"]
                for d in fb["districts"]}
    except Exception:  # noqa: BLE001 — no index, no name check; link check holds
        return {}


def identity_problems(rows: list[dict]) -> list[str]:
    """THE critical property, same as the laptop script's verify_targets:
    every superintendent gets THEIR report. Checked against the committed
    fallback index so a crossed wire in the contact table fails here, not in
    an inbox."""
    problems = []
    site_name = _site_names()
    for row in rows:
        num, name = row["district_number"], row["district_name"]
        if not row["deep_link"].endswith(f"?d={num}"):
            problems.append(f"{num} {name}: deep link points elsewhere "
                            f"({row['deep_link']})")
        page = site_name.get(num)
        if page is not None and page.casefold() != name.casefold():
            problems.append(f"{num}: contact row says {name!r} but the site "
                            f"page for that number says {page!r}")
        for k in ("insight_bonds", "insight_debt", "insight_trend", "hook"):
            if row.get(k) and name not in row[k]:
                problems.append(f"{num} {name}: {k} names a different "
                                f"district: {row[k][:80]!r}")
        if name not in row["subject"]:
            problems.append(f"{num} {name}: subject lacks the district name")
    return problems


# Eligibility is decided IN the database, against the same tables the sends
# write, so there is no local file whose loss shrinks a skip-list. Opt-outs
# compare lower-cased on both sides, matching the laptop script.
# One touch per DISTRICT, not only per address: a roster refresh gives a
# district with a new superintendent a NEW address that would sail past an
# address-only skip-list — re-mailing a district that was already contacted,
# just to a different person (the outreach skill's rule, now a WHERE clause).
# Re-introducing such districts is an owner decision made by hand, never a
# default the next enqueue takes silently.
ELIGIBLE_SQL = """
SELECT c.district_number, c.district_name, c.email, c.greeting, c.subject,
       c.deep_link, c.hook, c.insight_bonds, c.insight_debt, c.insight_trend
FROM public.outreach_contact c
WHERE c.email NOT IN (SELECT email FROM public.outreach_sent)
  AND lower(c.email) NOT IN
      (SELECT lower(email) FROM public.outreach_optout)
  AND c.email NOT IN (SELECT email FROM public.outreach_queue)
  AND c.district_number NOT IN
      (SELECT district_number FROM public.outreach_sent
       WHERE district_number IS NOT NULL AND district_number <> '')
  AND c.district_number NOT IN
      (SELECT district_number FROM public.outreach_queue)
ORDER BY c.district_number
"""

# Claim atomically so two drains (the cron and a manual kick) take disjoint
# rows; the send itself happens outside any transaction because holding a
# lock across an external HTTP call through a transaction-mode pooler is how
# connections die mid-DDL.
CLAIM_SQL = """
UPDATE public.outreach_queue q
SET status = 'sending', claimed_at = now()
WHERE q.id IN (
    SELECT id FROM public.outreach_queue
    WHERE status = 'queued'
    ORDER BY district_number
    LIMIT $1
    FOR UPDATE SKIP LOCKED)
RETURNING q.id, q.district_number, q.email, q.campaign
"""


async def enqueue(pool, limit: int, campaign: str,
                  write: bool = True) -> tuple[int, dict]:
    """State the wave. Returns (http_status, payload); sends nothing.

    With write=False this is the PREVIEW: the same selection, the same
    refusals, zero writes — the runbook's "real review" step, which the
    laptop flow made mandatory and an HTTP enqueue must not lose. The
    endpoint maps confirm="PREVIEW" here, so an owner can see exactly which
    districts a GO would queue before saying GO.
    """
    async with pool.acquire() as conn:
        # The watermark guard, server-side. On this database the sent table
        # is the durable record itself, so a count below the committed floor
        # means the WRONG DATABASE (a fork, a fresh project) — refusing is
        # even more right here than it was on a laptop.
        sent_count = await conn.fetchval(
            "SELECT count(*) FROM public.outreach_sent")
        floor = watermark_floor()
        if sent_count < floor:
            return 409, {"refused": (
                f"outreach_sent holds {sent_count} rows but the committed "
                f"watermark records {floor} addresses already emailed. A "
                f"skip-list cannot shrink — this looks like the wrong "
                f"database, and sending would re-email people who already "
                f"heard from us.")}

        rows = [dict(r) for r in await conn.fetch(ELIGIBLE_SQL)]
        bad = suppressed_digests()
        rows = [r for r in rows if _digest(r["email"]) not in bad]
        # ONE emptiness guard, after every filter: the campaign tail can be
        # all-suppressed, and reading take[0] off an empty selection was a
        # 500 to the operator instead of this answer.
        if not rows:
            return 200, {"enqueued": 0, "eligible": 0,
                         "note": "nobody eligible — the contact table may "
                                 "need a sync (scripts/sync_outreach_contacts"
                                 ".py), or everyone reachable has been "
                                 "mailed or suppressed"}
        problems = identity_problems(rows)
        if problems:
            return 409, {"refused": f"{len(problems)} rows would send "
                                    f"someone else's report; nothing was "
                                    f"queued.", "first": problems[:10]}
        eligible = len(rows)
        take = rows[:limit] if limit else rows

        if not write:
            return 200, {"would_enqueue": len(take), "eligible": eligible,
                         "campaign": campaign,
                         "first": take[0]["district_number"],
                         "last": take[-1]["district_number"],
                         "districts": [r["district_number"] for r in take],
                         "note": "preview only — nothing was queued; POST "
                                 "again with confirm=GO to queue exactly "
                                 "this selection"}

        # UNIQUE(email) makes a concurrent double-enqueue a no-op, not a
        # duplicate; executemany runs in one implicit transaction.
        await conn.executemany(
            "INSERT INTO public.outreach_queue "
            "(district_number, email, campaign) VALUES ($1, $2, $3) "
            "ON CONFLICT (email) DO NOTHING",
            [(r["district_number"], r["email"], campaign) for r in take])
        queued = await conn.fetchval(
            "SELECT count(*) FROM public.outreach_queue "
            "WHERE status = 'queued'")
    return 200, {"enqueued": len(take), "eligible": eligible,
                 "campaign": campaign, "queued_total": int(queued),
                 "first": take[0]["district_number"],
                 "last": take[-1]["district_number"],
                 "note": "nothing sent — the daily drain (or a manual kick "
                         "of /api/cron/outreach-drain) sends "
                         f"{BATCH} per invocation"}


async def drain(pool) -> tuple[int, dict]:
    """Send one batch from the queue. Safe to fire any number of times.

    Failure discipline, in order of what each failure can have cost:
      * BEFORE any /emails call (domain check down, wall clock hit, contact
        row wrong) — the claim is RELEASED back to 'queued'; provably nothing
        was sent, so retrying is free.
      * The /emails call itself raises — the row is marked 'error'; Resend
        refused, nothing was delivered.
      * AFTER Resend accepts — the message is GONE, so no failure past that
        point may ever read as anything but sent: a log-write failure marks
        the row 'sent' with the failure in detail, never 'error', because an
        operator who retries an "error" that was actually delivered re-emails
        a named official.
    """
    key = os.environ.get("RESEND_API_KEY", "").strip()
    postal = os.environ.get("TAG_POSTAL_ADDRESS", "").strip()
    if not key or not postal:
        missing = [n for n, v in [("RESEND_API_KEY", key),
                                  ("TAG_POSTAL_ADDRESS", postal)] if not v]
        return 200, {"status": "unarmed",
                     "missing": missing,
                     "note": "queue untouched; add the missing variables in "
                             "Vercel and the next drain sends"}

    from_addr = (os.environ.get("RESEND_FROM", "").strip()
                 or "Gus Sanchez <gus@ubntag.com>")
    bcc_addr = os.environ.get("TAG_BCC", "gus@ubntag.com").strip()
    unsub_addr = (os.environ.get("RESEND_REPLY_TO") or from_addr).split(
        "<")[-1].rstrip(">")
    unsubscribe = f"mailto:{unsub_addr}?subject=unsubscribe"

    started = time.monotonic()
    async with pool.acquire() as conn:
        async with conn.transaction():
            claimed = [dict(r) for r in await conn.fetch(CLAIM_SQL, BATCH)]
        if not claimed:
            return 200, {"status": "empty", "sent": 0,
                         "note": "no queued messages"}

        async def release(rows, why: str) -> None:
            """Provably-unsent rows go straight back to the queue."""
            if rows:
                await conn.executemany(
                    "UPDATE public.outreach_queue SET status = 'queued', "
                    "claimed_at = NULL, detail = $2 WHERE id = $1",
                    [(r["id"], why) for r in rows])

        # The domain check costs one API call and catches the config error
        # that would otherwise bounce a whole batch into spam folders. Any
        # failure HERE is before the first send, so the claim is released —
        # a Resend blip at cron time must not quarantine fifteen rows.
        try:
            verified = await run_in_threadpool(
                outreach_email.domain_verified, key, from_addr)
        except Exception as exc:  # noqa: BLE001 — released, not quarantined
            await release(claimed, "released: domain check unavailable")
            return 503, {"error": f"could not verify the sending domain "
                                  f"({exc}); batch released to the queue"}
        if not verified:
            await release(claimed, "released: domain not verified")
            return 503, {"error": f"sending domain of {from_addr!r} is not "
                                  f"verified in Resend; batch released back "
                                  f"to the queue"}

        contacts = {r["district_number"]: dict(r) for r in await conn.fetch(
            "SELECT * FROM public.outreach_contact "
            "WHERE district_number = ANY($1)",
            [r["district_number"] for r in claimed])}
        optout = {r["email"].lower() for r in await conn.fetch(
            "SELECT email FROM public.outreach_optout")}
        bad = suppressed_digests()

        sent = failed = skipped = released = 0
        # The loop is guarded whole: an unexpected DB error mid-batch (the
        # pooler dropping the connection during a bookkeeping UPDATE) would
        # otherwise propagate and strand every not-yet-attempted row in
        # 'sending' quarantine — violating this function's own promise that
        # pre-attempt failures release. `attempted` marks the one ambiguous
        # row: once its Resend call has STARTED it may have left and is never
        # released; every row after it provably has not.
        i, attempted = 0, False
        try:
            for i, q in enumerate(claimed):
                attempted = False
                # Wall-clock guard: the platform kills the invocation at its
                # duration cap, and rows claimed but never attempted would be
                # stranded in quarantine. Stopping early and RELEASING them is
                # free — nothing was attempted.
                if time.monotonic() - started > WALL_BUDGET_S:
                    remaining_rows = claimed[i:]
                    await release(remaining_rows, "released: invocation budget")
                    released += len(remaining_rows)
                    break

                row = contacts.get(q["district_number"])
                # Every per-recipient rail is re-held at SEND time, not only at
                # enqueue — the queue can sit for weeks while the contact table,
                # the opt-out list and the suppression file all move:
                #   * an opt-out recorded after enqueue is still honoured (the
                #     promise beats the queue);
                #   * a suppression hash added after enqueue still blocks (a
                #     known-dead address burns sender reputation);
                #   * a contact row whose ADDRESS changed no longer matches the
                #     queued address — a superintendent change; the owner
                #     decides, not a drain;
                #   * the identity gate re-runs on the CURRENT row, because the
                #     row rendered is not the row enqueue checked.
                if row is None:
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'error', "
                        "detail = 'contact row gone' WHERE id = $1", q["id"])
                    skipped += 1
                    continue
                if q["email"].lower() in optout:
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'error', "
                        "detail = 'opted out after enqueue' WHERE id = $1",
                        q["id"])
                    skipped += 1
                    continue
                if _digest(q["email"]) in bad:
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'error', "
                        "detail = 'suppressed after enqueue' WHERE id = $1",
                        q["id"])
                    skipped += 1
                    continue
                if row["email"] != q["email"]:
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'error', "
                        "detail = 'contact address changed since enqueue' "
                        "WHERE id = $1", q["id"])
                    skipped += 1
                    continue
                gate = identity_problems([row])
                if gate:
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'error', "
                        "detail = $2 WHERE id = $1", q["id"],
                        ("identity gate: " + gate[0])[:300])
                    skipped += 1
                    continue

                rid = tracking.new_rid()
                body, text = outreach_email.render_email(
                    row, postal, unsubscribe, rid=rid)
                payload = {
                    "from": from_addr, "to": [q["email"]],
                    "reply_to": os.environ.get("RESEND_REPLY_TO", from_addr),
                    "subject": row["subject"], "html": body, "text": text,
                    "headers": {"List-Unsubscribe": f"<{unsubscribe}>"}}
                if bcc_addr:
                    payload["bcc"] = [bcc_addr]
                attempted = True
                try:
                    got = await run_in_threadpool(
                        outreach_email.resend_request, "/emails", key, payload,
                        RESEND_TIMEOUT_S)
                except Exception as exc:  # noqa: BLE001 — refused or timed out; NOT retried
                    # A timeout is NOT "provably unsent" — Resend may have
                    # accepted before the socket died — so this marks the row
                    # for a human and never releases it for a retry.
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'error', "
                        "detail = $2 WHERE id = $1", q["id"], str(exc)[:300])
                    failed += 1
                    await asyncio.sleep(THROTTLE_S)
                    continue

                # Resend ACCEPTED — the message exists in the world. From here
                # every outcome must read as sent; a logging failure is a
                # bookkeeping problem, never a reason to let a retry re-send.
                mid = got.get("id", "")
                sent += 1
                try:
                    await conn.execute(
                        "INSERT INTO public.outreach_sent "
                        "(email, district_number, message_id, sent_at) "
                        "VALUES ($1, $2, $3, now()) "
                        "ON CONFLICT (email) DO NOTHING",
                        q["email"], q["district_number"], mid)
                    await conn.execute(
                        "INSERT INTO public.outreach_recipient "
                        "(rid, email, district_number, campaign, message_id) "
                        "VALUES ($1, $2, $3, $4, $5) "
                        "ON CONFLICT (rid) DO NOTHING",
                        rid, q["email"], q["district_number"], q["campaign"], mid)
                    await conn.execute(
                        "UPDATE public.outreach_queue SET status = 'sent', "
                        "sent_at = now(), detail = $2 WHERE id = $1",
                        q["id"], mid)
                except Exception as exc:  # noqa: BLE001 — delivered; record that above all
                    print(f"WARNING: message {mid} to district "
                          f"{q['district_number']} was DELIVERED but logging "
                          f"failed ({exc}) — reconcile against Resend before "
                          f"any retry.")
                    try:
                        await conn.execute(
                            "UPDATE public.outreach_queue SET status = 'sent', "
                            "sent_at = now(), detail = $2 WHERE id = $1",
                            q["id"],
                            f"sent; log write failed: {exc}"[:300])
                    except Exception:  # noqa: BLE001 — nothing left to try
                        print(f"WARNING: could not even mark queue row "
                              f"{q['id']} sent — it will surface as stale "
                              f"'sending'; message id {mid}.")
                if i < len(claimed) - 1:      # no pointless sleep after the last
                    await asyncio.sleep(THROTTLE_S)

        except Exception as exc:  # noqa: BLE001 — release what provably never left
            leftover = claimed[i + 1:] if attempted else claimed[i:]
            try:
                await release(leftover, "released: drain aborted mid-batch")
                released += len(leftover)
            except Exception:  # noqa: BLE001 — the connection itself is gone
                print(f"WARNING: drain aborted ({exc}) and "
                      f"{len(leftover)} unattempted rows could not be "
                      f"released — ids "
                      f"{[r['id'] for r in leftover]}; they will surface "
                      f"as stale 'sending'.")
            return 500, {"error": f"drain aborted mid-batch ({exc})",
                         "sent": sent, "failed": failed,
                         "skipped": skipped, "released": released}

        remaining = await conn.fetchval(
            "SELECT count(*) FROM public.outreach_queue "
            "WHERE status = 'queued'")
    return 200, {"status": "drained", "sent": sent, "failed": failed,
                 "skipped": skipped, "released": released,
                 "remaining": int(remaining),
                 "seconds": round(time.monotonic() - started, 1)}


async def status(pool) -> dict:
    """The queue at a glance, plus anything a human should look at."""
    async with pool.acquire() as conn:
        counts = {r["status"]: int(r["n"]) for r in await conn.fetch(
            "SELECT status, count(*) AS n FROM public.outreach_queue "
            "GROUP BY status")}
        stale = [dict(r) for r in await conn.fetch(
            "SELECT district_number, claimed_at FROM public.outreach_queue "
            "WHERE status = 'sending' "
            "AND claimed_at < now() - make_interval(secs => $1)",
            STALE_SENDING_S)]
        sent_total = await conn.fetchval(
            "SELECT count(*) FROM public.outreach_sent")
        contacts = await conn.fetchval(
            "SELECT count(*) FROM public.outreach_contact")
        errors = [dict(r) for r in await conn.fetch(
            "SELECT district_number, detail FROM public.outreach_queue "
            "WHERE status = 'error' ORDER BY id DESC LIMIT 10")]
    return {
        "queue": counts, "contacts": int(contacts),
        "sent_all_time": int(sent_total),
        "watermark_floor": watermark_floor(),
        "armed": bool(os.environ.get("RESEND_API_KEY", "").strip()
                      and os.environ.get("TAG_POSTAL_ADDRESS", "").strip()),
        "stale_sending": stale,
        "recent_errors": errors,
        "limits": ["A 'sending' row older than an hour means a drain died "
                   "mid-message; it is never auto-retried because the "
                   "message may have left — decide by checking Resend for "
                   "that address before re-queueing by hand.",
                   f"Each drain sends at most {BATCH} messages; kick "
                   "/api/cron/outreach-drain repeatedly to move faster than "
                   "the daily schedule."]}

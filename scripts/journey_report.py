"""What each outreach recipient did, from send to latest visit.

Reads the tables written by src/tracking.py and prints two things: a funnel
across the whole campaign, and — with --email or --top — a per-person
timeline of every recorded event.

    python scripts/journey_report.py                     # funnel + hottest 20
    python scripts/journey_report.py --campaign w2
    python scripts/journey_report.py --email x@y.isd.net # one person, in full
    python scripts/journey_report.py --csv out.csv       # the roster

Environment
-----------
    SUPABASE_PAT   required — reads via the Management API, because direct
                   Postgres (5432/6543) is blocked from dev containers

A note on reading these numbers honestly, since the whole point of this
project is not fooling yourself:

  * An OPEN is a pixel load. Apple Mail Privacy Protection and corporate
    scanners fetch it with no human present, so opens are an upper bound.
  * A CLICK is a real human action — the pixel cannot forge one, and the token
    is only in that one email.
  * DWELL is visible time, flushed on tab-hide and every 60s. A reader who
    closes the laptop lid mid-page loses the last span.
  * A RETURN is a new session (>30 min gap) with no fresh token in the URL —
    they came back on their own. It is the strongest signal in the table.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT_REF = "zwhvabkvrexphlskubog"


def sql(query: str, pat: str) -> list[dict]:
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"Bearer {pat}",
                 "User-Agent": "txisd-journey/1.0",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def _mins(ms) -> str:
    if not ms:
        return "—"
    seconds = int(ms) // 1000
    return f"{seconds // 60}m{seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# Telling a superintendent from a mail-security appliance.
#
# School districts run Microsoft Defender / Barracuda / Mimecast, which open
# every message and follow every link within seconds to check them. In the raw
# counters they look exactly like eager readers, so the funnel classifies each
# clicker instead of counting them all.
#
# THE SIGNAL THAT ACTUALLY WORKS: `dwell` is the only event this system records
# that REQUIRES JavaScript to execute in a real rendering engine, with the tab
# actually visible for at least a second (static/track.js). `click` and
# `pageview` are written server-side by the HTTP request itself, so a scanner
# fetching the URL produces both and proves nothing.
#
# A first version of this filter used click LATENCY (reject anything under two
# minutes) plus a dead-browser list. It was wrong in the expensive direction:
# it threw away seven recipients who had genuinely rendered the page, because
# some people really do read mail within seconds of it arriving. Latency is
# evidence about machines, never about humans — a fast click is not a fake one.
# Keep that lesson: an over-aggressive filter is just as wrong as no filter,
# and it is more dangerous because it feels rigorous.
#
# The remaining ambiguity is real and is reported rather than hidden. Some
# appliances detonate links in a genuine headless browser, which can produce a
# dwell event. Their tell is FAN-OUT: one recipient generating clicks from many
# different user agents across many sessions over hours. One person does not
# own thirteen browsers.
MAX_HUMAN_USER_AGENTS = 4   # above this, a browser farm is in the mix


def _classify_sql(campaign_filter: str) -> str:
    """Per-recipient behaviour, from the events themselves."""
    return f"""
        SELECT r.rid,
               count(*) FILTER (WHERE e.event = 'dwell')   AS js_events,
               count(DISTINCT e.user_agent)                AS uas
        FROM public.visitor_event e
        JOIN public.outreach_recipient r ON r.rid = e.rid
        WHERE r.rid IN (SELECT rid FROM public.visitor_event WHERE event = 'click')
          {campaign_filter}
        GROUP BY r.rid"""


def funnel(pat: str, campaign: str | None) -> None:
    where = f"WHERE campaign = {_q(campaign)}" if campaign else ""
    rows = sql(f"""
        SELECT count(*) AS sent,
               count(*) FILTER (WHERE opens      > 0) AS opened,
               count(*) FILTER (WHERE first_click_at IS NOT NULL) AS clicked,
               count(*) FILTER (WHERE sessions   > 1) AS returned,
               coalesce(sum(pageviews), 0)            AS pageviews,
               coalesce(sum(total_dwell_ms), 0)       AS dwell
        FROM public.v_recipient_journey {where}""", pat)
    if not rows:
        print("no recipients recorded yet")
        return
    r = rows[0]
    sent = int(r["sent"]) or 1

    # Classify every clicker by what their browser actually did.
    ewhere = f"AND r.campaign = {_q(campaign)}" if campaign else ""
    people = sql(_classify_sql(ewhere), pat)
    confirmed = sum(1 for p in people
                    if int(p["js_events"]) > 0
                    and int(p["uas"]) <= MAX_HUMAN_USER_AGENTS)
    mixed = sum(1 for p in people
                if int(p["js_events"]) > 0
                and int(p["uas"]) > MAX_HUMAN_USER_AGENTS)
    machine = sum(1 for p in people if int(p["js_events"]) == 0)

    def pct(n) -> str:
        return f"{int(n) / sent * 100:5.1f}%"

    print(f"\n  CAMPAIGN {campaign or '(all)'}\n")
    print(f"  {'sent':<28}{int(r['sent']):>7}")
    print(f"  {'came back later':<28}{int(r['returned']):>7}   {pct(r['returned'])}")
    print(f"\n  CLICKED — raw counter{'':<7}{int(r['clicked']):>7}   {pct(r['clicked'])}")
    print(f"    {'confirmed human':<26}{confirmed:>7}   {pct(confirmed)}"
          "   rendered the page in a real browser")
    print(f"    {'ambiguous (browser farm)':<26}{mixed:>7}   {pct(mixed)}"
          "   a human may be inside this")
    print(f"    {'machine only':<26}{machine:>7}   {pct(machine)}"
          "   never executed JavaScript")
    print(f"\n  {'HONEST CLICK RANGE':<28}{confirmed:>3}–{confirmed + mixed:<3}"
          f"   {pct(confirmed)}–{pct(confirmed + mixed).strip()}")
    print(f"\n  {'opened — raw pixel':<28}{int(r['opened']):>7}   {pct(r['opened'])}"
          "   NOT trustworthy, see below")
    print(f"\n  {'pages read':<28}{int(r['pageviews']):>7}")
    print(f"  {'total time on site':<28}{_mins(r['dwell']):>7}")
    print("""
  How a clicker is classified — and what each grade is worth:
    confirmed human   a `dwell` event exists, which only fires when JavaScript
                      runs in a real engine with the tab VISIBLE for >=1s.
                      Server-side click/pageview records prove nothing: a
                      scanner fetching the URL writes both.
    ambiguous         rendered the page, but this recipient produced clicks
                      from more than %d user agents across many sessions.
                      That is an appliance farm; a real reader may be inside
                      it, so it is neither counted nor discarded.
    machine only      fetched the link and never ran a line of JavaScript.

  OPENS are not classifiable at all: the pixel is fired by scanners that
  never showed a human the message, and blocked entirely by clients that
  suppress images. Quote the click range; never quote an open rate.""" %
          MAX_HUMAN_USER_AGENTS)


def roster(pat: str, campaign: str | None, limit: int) -> list[dict]:
    """The engaged, most-engaged first. Recipients with no page view at all are
    excluded: this is a follow-up worklist, not a mailing list."""
    clauses = ["pageviews > 0"]
    if campaign:
        clauses.append(f"campaign = {_q(campaign)}")
    where = " AND ".join(clauses)
    return sql(f"""
        SELECT email, district_number, opens, pageviews, sessions,
               distinct_pages, total_dwell_ms,
               to_char(first_click_at, 'MM-DD HH24:MI') AS clicked_at,
               to_char(last_seen_at,   'MM-DD HH24:MI') AS last_seen
        FROM public.v_recipient_journey
        WHERE {where}
        ORDER BY total_dwell_ms DESC NULLS LAST, pageviews DESC
        LIMIT {int(limit)}""", pat)


def timeline(pat: str, email: str) -> None:
    rows = sql(f"""
        SELECT r.email, r.district_number, r.campaign,
               to_char(e.occurred_at, 'YYYY-MM-DD HH24:MI:SS') AS at,
               e.event, e.path, e.district_number AS viewed, e.dwell_ms,
               e.device, e.session_id
        FROM public.visitor_event e
        JOIN public.outreach_recipient r ON r.rid = e.rid
        WHERE lower(r.email) = lower({_q(email)})
        ORDER BY e.occurred_at""", pat)
    if not rows:
        print(f"no events recorded for {email}")
        return
    print(f"\n  {email} · district {rows[0]['district_number']} "
          f"· campaign {rows[0]['campaign']}\n")
    session = None
    for r in rows:
        if r["session_id"] != session:
            session = r["session_id"]
            print(f"  ── session {session[:6]} " + "─" * 44)
        detail = r["path"] or ""
        if r["viewed"]:
            detail += f"  (district {r['viewed']})"
        if r["dwell_ms"]:
            detail += f"  {_mins(r['dwell_ms'])}"
        print(f"  {r['at']}  {r['event']:<11}{detail}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", default=None, help="limit to one wave, e.g. w2")
    ap.add_argument("--email", default=None, help="full timeline for one recipient")
    ap.add_argument("--top", type=int, default=20, help="rows in the roster")
    ap.add_argument("--csv", default=None, help="write the roster to a file")
    args = ap.parse_args()

    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        print("SUPABASE_PAT is not set — cannot read the journey tables.")
        return 1

    if args.email:
        timeline(pat, args.email)
        return 0

    funnel(pat, args.campaign)
    rows = roster(pat, args.campaign, args.top)
    if rows:
        print(f"\n  MOST ENGAGED ({len(rows)})\n")
        print(f"  {'district':<9}{'email':<38}{'opens':>6}{'pages':>6}"
              f"{'visits':>7}{'time':>8}  clicked")
        for r in rows:
            print(f"  {r['district_number']:<9}{r['email'][:37]:<38}"
                  f"{int(r['opens'] or 0):>6}{int(r['pageviews'] or 0):>6}"
                  f"{int(r['sessions'] or 0):>7}"
                  f"{_mins(r['total_dwell_ms']):>8}  {r['clicked_at'] or '—'}")
    else:
        print("\n  Nobody has clicked through yet.")

    if args.csv and rows:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  roster written to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

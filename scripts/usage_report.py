#!/usr/bin/env python3
"""What's happening on the site: visitors, pages, and what people asked.

Reads the first-party counters (public.site_visits, public.nlp_questions) over
the Supabase Management API — no direct Postgres needed, so it runs from
anywhere. Nothing here can identify a person: page views are daily totals and
questions are stored on their own. See sql/create_analytics.sql.

    export SUPABASE_PAT=sbp_...          # rotate first if it has been shared
    python scripts/usage_report.py               # last 30 days
    python scripts/usage_report.py --days 7      # last week
    python scripts/usage_report.py --questions 50
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "zwhvabkvrexphlskubog")
UA = "texas-isd-finances/1.0 (+https://txisd.dev)"


def run_sql(query: str, pat: str):
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": query}).encode(), method="POST",
        headers={"Authorization": f"Bearer {pat}", "Content-Type": "application/json",
                 "User-Agent": UA})          # UA matters: Cloudflare 403s urllib's default
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as e:
        print(f"query failed: HTTP {e.code} {e.read().decode(errors='replace')[:200]}",
              file=sys.stderr)
        return []


def table(rows, cols, widths):
    if not rows:
        print("   (nothing yet)")
        return
    print("   " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("   " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("   " + "  ".join(str(r.get(c, ""))[:w].ljust(w)
                                for c, w in zip(cols, widths)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--questions", type=int, default=25)
    args = ap.parse_args()

    pat = os.getenv("SUPABASE_PAT")
    if not pat:
        print("SUPABASE_PAT is not set.\n    export SUPABASE_PAT=sbp_...", file=sys.stderr)
        return 2
    d = args.days

    print(f"\n=== TXISD.DEV — last {d} days ===\n")

    tot = run_sql(f"SELECT coalesce(sum(hits),0) AS v, count(distinct day) AS days "
                  f"FROM public.site_visits WHERE day >= current_date - {d};", pat)
    if tot:
        v, days = tot[0]["v"], tot[0]["days"] or 1
        print(f"  {v} page views over {days} day(s)  (~{round(v/days,1)}/day)\n")

    print("  TOP PAGES")
    table(run_sql(f"SELECT path, sum(hits) AS views FROM public.site_visits "
                  f"WHERE day >= current_date - {d} GROUP BY path "
                  f"ORDER BY views DESC LIMIT 15;", pat),
          ["path", "views"], [28, 7])

    print("\n  DEVICES")
    table(run_sql(f"SELECT device, sum(hits) AS views FROM public.site_visits "
                  f"WHERE day >= current_date - {d} GROUP BY device "
                  f"ORDER BY views DESC;", pat),
          ["device", "views"], [12, 7])

    print("\n  WHERE THEY CAME FROM  (blank = direct / typed the address)")
    table(run_sql(f"SELECT coalesce(nullif(referrer_host,''),'(direct)') AS source, "
                  f"sum(hits) AS views FROM public.site_visits "
                  f"WHERE day >= current_date - {d} GROUP BY 1 "
                  f"ORDER BY views DESC LIMIT 12;", pat),
          ["source", "views"], [30, 7])

    print("\n  BY DAY")
    table(run_sql(f"SELECT day::text AS day, sum(hits) AS views "
                  f"FROM public.site_visits WHERE day >= current_date - {d} "
                  f"GROUP BY day ORDER BY day DESC LIMIT 14;", pat),
          ["day", "views"], [12, 7])

    qs = run_sql(f"SELECT count(*) AS n, count(*) FILTER (WHERE NOT ok) AS failed, "
                 f"round(avg(ms)) AS avg_ms FROM public.nlp_questions "
                 f"WHERE asked_at >= now() - interval '{d} days';", pat)
    if qs:
        n, failed, avg = qs[0]["n"], qs[0]["failed"], qs[0]["avg_ms"]
        print(f"\n  QUESTIONS ASKED: {n}   failed: {failed}   avg {avg or 0} ms")
        if failed and n and failed / n > 0.2:
            print("   ⚠ more than a fifth failed — check the OpenAI balance and the logs")

    print(f"\n  WHAT PEOPLE ASKED (most recent {args.questions})")
    table(run_sql(f"SELECT to_char(asked_at,'MM-DD HH24:MI') AS when, "
                  f"CASE WHEN ok THEN '' ELSE 'FAIL' END AS bad, question "
                  f"FROM public.nlp_questions ORDER BY asked_at DESC "
                  f"LIMIT {args.questions};", pat),
          ["when", "bad", "question"], [12, 4, 78])
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

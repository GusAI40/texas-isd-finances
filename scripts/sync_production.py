#!/usr/bin/env python3
"""Bring production in line with the repo: DB migrations, then the deploy step.

What's out of sync (checked 2026, this branch vs live):
  - Supabase is missing two tables this session added: the /query spend ceiling
    (create_nlp_usage.sql) and the ISD-intelligence store (create_isd_intel.sql).
  - Vercel production runs older code — /heatmap, /intel, the cron, dark mode
    are not live — because production deploys from a working tree, not from git.

This script does the database half, which is safe to automate and idempotent,
then prints the Vercel half, which a human should run and watch.

Credentials come from the ENVIRONMENT, never arguments (arguments leak into
shell history and `ps`). Rotate first — every token pasted into a chat this
session must be treated as public — then:

    export SUPABASE_PAT=sbp_...          # the freshly rotated one
    python scripts/sync_production.py            # apply + verify the migrations
    python scripts/sync_production.py --check     # verify only, change nothing

The Vercel deploy is intentionally NOT automated here: it ships the whole
front end and should be run where its output can be watched.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "zwhvabkvrexphlskubog")
USER_AGENT = "texas-isd-finances/1.0 (+https://txisd.dev)"

# The migrations this session added, in apply order. Each is idempotent, so a
# re-run is a no-op — safe to run against a database that already has some.
MIGRATIONS = [
    ("create_nlp_usage.sql", "public.nlp_usage",
     "the /query spend ceiling (per-minute + per-day, shared across instances)"),
    ("create_isd_intel.sql", "public.isd_briefings",
     "the daily ISD-intelligence briefing + review-queue store"),
    ("create_analytics.sql", "public.site_visits",
     "first-party usage counting (daily page-view totals + asked questions)"),
]


class Fail(Exception):
    pass


def call(url: str, pat: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {pat}", "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})   # UA matters: Cloudflare 403s urllib's default
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise Fail(f"{method} {url.split('?')[0]} → HTTP {e.code}: "
                   f"{e.read().decode(errors='replace')[:300]}") from None


def run_sql(query: str, pat: str):
    return call(f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
                pat, "POST", {"query": query})


def table_exists(qualified: str, pat: str) -> bool:
    schema, name = qualified.split(".", 1)
    rows = run_sql(
        f"SELECT to_regclass('{schema}.{name}') IS NOT NULL AS present", pat)
    return bool(rows and rows[0].get("present"))


def main() -> int:
    check_only = "--check" in sys.argv
    pat = os.getenv("SUPABASE_PAT")
    print(f"Target: Supabase project {PROJECT_REF}\n")

    if not pat:
        print("SUPABASE_PAT is not set. Rotate the token first (it has been pasted "
              "into chat), then:\n    export SUPABASE_PAT=sbp_...\n    "
              "python scripts/sync_production.py", file=sys.stderr)
        return 2

    applied, already = [], []
    try:
        for filename, table, desc in MIGRATIONS:
            path = SQL_DIR / filename
            if not path.exists():
                raise Fail(f"missing {path}")
            here = table_exists(table, pat)
            if check_only:
                print(f"  [{'ok' if here else 'MISSING'}] {table:<26} — {desc}")
                continue
            if here:
                print(f"  already present: {table}  ({desc})")
                already.append(table)
                continue
            print(f"  applying {filename} → {table} …")
            run_sql(path.read_text(), pat)
            if not table_exists(table, pat):
                raise Fail(f"{filename} ran but {table} still does not exist")
            print(f"     ok: {table}")
            applied.append(table)
    except Fail as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        return 1

    if check_only:
        return 0

    print(f"\nDatabase in sync — {len(applied)} applied, {len(already)} already present.")
    print("\n" + "=" * 68)
    print("Now ship the code. Production deploys from the working tree, NOT from")
    print("git, so a fresh checkout of this branch is what should be deployed:")
    print("""
    git checkout claude/audit-public-launch-ocd7ra && git pull
    # optional, for zoomable Mapbox tiles on /heatmap (public pk. token only):
    vercel env add MAPBOX_TOKEN production   --scope tag-ai-projects
    # required for the daily cron; generate with: openssl rand -base64 32
    vercel env add CRON_SECRET production    --scope tag-ai-projects
    vercel deploy --prod --scope tag-ai-projects
""")
    print("Then verify: curl -s https://txisd.dev/heatmap -o /dev/null -w '%{http_code}\\n'")
    print("(expect 200). NLP_DB_URL is already set from the C-1 fix; leave it.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

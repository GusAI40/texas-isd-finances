"""Push the mailing list into the database, where the site can send from it.

The merge CSV (data/outreach_merge.csv) is gitignored contact data that has
already died with a container once — the 2026-08-19 root cause. The durable
home is public.outreach_contact, which the deployed site's enqueue reads.
This script is the bridge: run it after any `build_outreach_merge.py`, from
any machine that has the CSV and a SUPABASE_PAT.

    python scripts/sync_outreach_contacts.py            # upsert all rows
    python scripts/sync_outreach_contacts.py --dry-run  # count, write nothing

Upsert by district_number: a roster refresh (a superintendent change) updates
the row in place. That is deliberate and safe because the SKIP-LIST keys on
addresses in outreach_sent — updating a contact never un-sends anything — but
remember the skill's rule: a district whose superintendent changed gets a NEW
address that sails past the address skip-list, so after a roster refresh,
enqueue decisions about re-introducing districts belong to the owner, not a
default.
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
MERGE = ROOT / "data" / "outreach_merge.csv"
PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "zwhvabkvrexphlskubog")
API = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"

FIELDS = ["district_number", "district_name", "email", "greeting", "subject",
          "deep_link", "hook", "insight_bonds", "insight_debt",
          "insight_trend"]
CHUNK = 100          # rows per statement — the Management API caps body size


def q(s: str) -> str:
    return "'" + (s or "").replace("'", "''") + "'"


def run_sql(query: str, pat: str) -> list[dict]:
    req = urllib.request.Request(
        API, data=json.dumps({"query": query}).encode(), method="POST",
        headers={"Authorization": f"Bearer {pat}",
                 "Content-Type": "application/json",
                 "User-Agent": "texas-isd-finances/1.0 (+https://txisd.dev)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
    return json.loads(raw) if raw else []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not MERGE.exists():
        print(f"{MERGE.relative_to(ROOT)} is missing — run "
              f"scripts/build_outreach_merge.py first.", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(MERGE.open()))
    missing = [f for f in FIELDS if rows and f not in rows[0]]
    if missing:
        print(f"merge file lacks columns the contact table needs: {missing}",
              file=sys.stderr)
        return 1
    print(f"{len(rows)} rows in {MERGE.relative_to(ROOT)}")
    if args.dry_run:
        print("dry run — nothing written")
        return 0

    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        print("SUPABASE_PAT is not set — export a Supabase personal access "
              "token first. Never pass it as an argument.", file=sys.stderr)
        return 2

    sets = ", ".join(f"{f} = excluded.{f}" for f in FIELDS[1:])
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        values = ",".join(
            "(" + ",".join(q(r[f]) for f in FIELDS) + ")" for r in chunk)
        run_sql(
            f"INSERT INTO public.outreach_contact ({', '.join(FIELDS)}) "
            f"VALUES {values} ON CONFLICT (district_number) DO UPDATE SET "
            f"{sets}, updated_at = now()", pat)
        print(f"  upserted {i + len(chunk)}/{len(rows)}")

    got = run_sql("SELECT count(*) AS n FROM public.outreach_contact", pat)
    remote = int(got[0]["n"]) if got else 0
    print(f"outreach_contact now holds {remote} rows (local file: {len(rows)})")
    if remote < len(rows):
        print("ERROR: remote holds fewer rows than the file after the push",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

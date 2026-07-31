#!/usr/bin/env python3
"""Build static/fallback_index.json — the site's survival kit for a dead database.

The problem this solves
-----------------------
Fourteen of the API's endpoints are served from committed JSON and need no
database at all: outcomes, economics, bonds, equity, the Houston takeover, both
maps. They would sail through a database outage untouched.

They didn't, because the front door is database-backed. The landing page awaits
/stats and /benchmarks before it renders anything, and the district search box
calls /districts. When the Supabase free tier pauses after a week idle — which
it does — a visitor got a blank page and no way to reach the fourteen sections
that were still perfectly healthy.

This file is the fallback. The district list comes from the committed payloads
themselves, so it lists exactly the districts that have static content to show:
a district absent from every payload has nothing to display even when the
database is up, so putting it in the picker would only promise a dead end.

The statewide figures cannot be derived from the payloads — they are medians
over the full finance table — so they are captured from a live source and
stamped with the date. They move only when TEA publishes, so a stale snapshot
is a slightly old number rather than a wrong one, and the page says so.

Usage
-----
    python scripts/build_fallback_index.py                 # payload data only
    python scripts/build_fallback_index.py --from-live     # also refresh stats

Rebuild it whenever a new TEA release changes the payloads.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
OUT = STATIC / "fallback_index.json"
LIVE = "https://txisd.dev"

# Every payload that keys districts by number. district_geo is deliberately
# included: a district with a boundary can be found on the map even if it has
# no finance record in the others.
PAYLOADS = {
    "economics_data.json": "districts",
    "outcomes_data.json": "districts",
    "equity_data.json": "districts",
    "bond_data.json": "districts",
    "district_geo.json": "d",
}


def district_index() -> list[dict]:
    """Union of every district that any committed payload can render."""
    names: dict[str, str] = {}
    found: set[str] = set()
    for filename, key in PAYLOADS.items():
        path = STATIC / filename
        if not path.exists():
            print(f"  ! {filename} missing — skipping", file=sys.stderr)
            continue
        blob = json.loads(path.read_text())
        section = blob.get(key) or {}
        found |= set(section)
        for num, rec in section.items():
            # First payload to supply a name wins; they agree where they overlap.
            if num not in names and isinstance(rec, dict):
                name = rec.get("district_name") or rec.get("name")
                if name:
                    names[num] = name
        print(f"  {filename}: {len(section)} districts")

    missing = sorted(found - set(names))
    if missing:
        print(f"  ! {len(missing)} districts have no name in any payload", file=sys.stderr)
    return [
        {"district_number": n, "district_name": names[n]}
        for n in sorted(found, key=lambda n: names.get(n, "zzz"))
        if n in names
    ]


def fetch(path: str):
    with urllib.request.urlopen(f"{LIVE}{path}", timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-live", action="store_true",
                    help=f"refresh the statewide figures from {LIVE}")
    args = ap.parse_args()

    print("Building the district index from committed payloads:")
    districts = district_index()
    print(f"  -> {len(districts)} districts with a name")

    payload = {}
    if OUT.exists():
        payload = json.loads(OUT.read_text())   # keep the previous snapshot

    if args.from_live or "stats" not in payload:
        print(f"Fetching statewide figures from {LIVE} …")
        try:
            payload["stats"] = fetch("/stats")
            payload["benchmarks"] = fetch("/benchmarks")
            # The statewide dollar is the headline of the whole page — the
            # first number a visitor sees. Without it the hero reads "$—",
            # which looks broken rather than degraded.
            payload["dollar_texas"] = fetch("/dollar/texas")
            payload["captured"] = date.today().isoformat()
            print(f"  -> stats, the statewide dollar, and "
                  f"{len(payload['benchmarks'])} benchmark years")
        except Exception as exc:
            print(f"  ! could not reach {LIVE}: {exc}", file=sys.stderr)
            if "stats" not in payload:
                print("  ! no previous snapshot to fall back on", file=sys.stderr)
                return 1
            print("  keeping the previous snapshot")

    payload["districts"] = districts
    payload["meta"] = {
        "purpose": "Served by /fallback-index when the database is unreachable, "
                   "so the picker and the statewide figures survive an outage.",
        "district_source": "union of the committed static payloads — exactly the "
                           "districts that have content to show without a database",
        "figures_captured": payload.get("captured"),
        "figures_note": "Statewide medians move only when TEA publishes. The page "
                        "labels them as a snapshot while the database is down.",
    }
    # Key order for a readable diff; districts last because it is the long one.
    ordered = {k: payload[k] for k in
               ("meta", "captured", "stats", "benchmarks", "dollar_texas", "districts")
               if k in payload}
    OUT.write_text(json.dumps(ordered, separators=(",", ":")))
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

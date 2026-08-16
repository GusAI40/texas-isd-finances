#!/usr/bin/env python3
"""Record which outreach addresses must never be mailed again — committably.

Why this exists
---------------
The first KPI snapshot found 11 addresses that can never receive an email:
6 hard bounces (dead mailboxes) and 5 suppressed by the provider. Mailing them
again would not reach anyone; it would only mark the sending domain as one
that keeps writing to dead addresses, which degrades delivery for every
FUTURE wave to every LIVE address.

Those addresses were already protected by the sent-log skip-list — but that
log is gitignored and container-only, and this repo has already once resolved
a skip-list of ZERO in a fresh container. The suppression must live in git.

Why hashes
----------
Outreach CSVs are deliberately never committed: they are contact data. A
SHA-256 of the lowercased address carries no contact information, cannot be
reversed into an inbox, and is exactly enough for the sender to answer the
only question it has: "is the address I am about to mail on this list?"

    python scripts/prune_bad_addresses.py            # rebuild from the KPI report
    python scripts/prune_bad_addresses.py --show     # count what is recorded

The output file data/outreach_suppression.json is committed. Entries are only
ever ADDED — an address that hard-bounced once is dead, and a provider
suppression means the provider knows something we don't. If an address is
later corrected, the DISTRICT gets mailed at its new address, which hashes
differently; nothing needs removing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KPI = ROOT / "data" / "outreach_kpi_report.csv"
OUT = ROOT / "data" / "outreach_suppression.json"

BLOCK = {"bounced", "suppressed", "complained"}


def digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def load() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"_what_this_is": (
        "SHA-256 hashes of lowercased email addresses that hard-bounced, were "
        "suppressed by the provider, or complained. The sender refuses these "
        "before any other check. Hashes, not addresses: contact data is never "
        "committed. Additive only — a dead mailbox does not come back, and a "
        "corrected district address hashes differently. Rebuilt by "
        "scripts/prune_bad_addresses.py from the KPI report."),
        "entries": {}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="report counts, change nothing")
    args = ap.parse_args()

    data = load()
    entries = data["entries"]

    if args.show:
        by = {}
        for v in entries.values():
            by[v["status"]] = by.get(v["status"], 0) + 1
        print(f"{len(entries)} suppressed address hashes: {by or 'none'}")
        return 0

    if not KPI.exists():
        print(f"{KPI} not present in this container — nothing to prune from. "
              "The committed suppression file is unchanged.", file=sys.stderr)
        return 1

    added = 0
    with KPI.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status") or "").strip() not in BLOCK:
                continue
            h = digest(row["email"])
            if h not in entries:
                entries[h] = {"status": row["status"].strip(),
                              "district_number": row.get("district_number", ""),
                              "recorded": date.today().isoformat()}
                added += 1

    OUT.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} — {len(entries)} entries ({added} new). "
          "Commit it: the sent-log that also covers these is container-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

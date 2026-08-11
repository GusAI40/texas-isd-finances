"""Pull Texas school bond elections from the agency that actually publishes them.

Why this script exists
----------------------
The bond layer shipped on `data/texas_bond_elections.csv`, an Excel export
handed over by a municipal-advisory vendor. Two things were wrong with that,
and only one of them was visible.

The visible one: it was stale. It stopped at 2024 and matched the state's own
file exactly through 2023, so nothing in the repo could tell the difference
between "complete" and "two years behind". 404 decided propositions were
missing — every one of them recent, which is to say every one of them the ones
a reader would ask about first. It also carried spreadsheet furniture: a
`Subtotal:` row, a `Grand Total:` row, a repeated header line and 46 blanks.

The invisible one was worse. `src/sources.py` credited the file to "compiled
county election returns (Texas Secretary of State)" and stated that no single
agency publishes school bond elections statewide. That is simply untrue. The
**Texas Bond Review Board** publishes all of them, statewide, back to 1958, as
an open dataset on the state's own Socrata portal, and it has done so all
along. `scripts/verify_sources.py` never caught it, because the Secretary of
State URL returns 200 — the verifier proved the link was alive, not that it
pointed at the right thing.

So this replaces a vendor's spreadsheet with the state's own API.

What the state adds that the vendor stripped
--------------------------------------------
The Socrata file carries a `source` column on every row, recording where the
Board got that particular record: its own filings (TBR), the issuer, the
Attorney General's bond registry (OAG), the Texas State Bulletin (TSB), a bond
buyer report (BB), or other. That is per-row provenance from the publisher,
and it survived into our CSV as `Source` rather than being thrown away.

Deliberately not ingested
-------------------------
The vendor shipped two companion files with this one. They contain that
vendor's private CRM — named sales representatives, deal revenue, commission
splits. They have never been read into this repo and must not be. Going
first-party removes the temptation permanently.

    python scripts/ingest_bond_elections.py
    python scripts/ingest_bond_elections.py --dry-run     # show the diff only

Exits non-zero if the endpoint is unreachable or returns implausibly few rows,
so a silent truncation cannot quietly shrink the published history.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The Bond Review Board's election dataset on the State of Texas open data
# portal. `kbmc-qmvg` is the dataset's permanent four-by-four identifier.
DATASET = "kbmc-qmvg"
ENDPOINT = f"https://data.texas.gov/resource/{DATASET}.json"
LANDING = f"https://data.texas.gov/d/{DATASET}"
PAGE = 5000
UA = "txisd-bond-ingest/1.0 (+https://txisd.dev/sources)"
TIMEOUT = 60

# Everything the portal calls a school district. The file also carries water
# districts, cities, counties, community-college and hospital districts; those
# are real elections but they are not this site's subject and cannot be
# resolved against a TEA district number.
ISD = "ISD"

# The column names `scripts/build_bond_data.py` reads. They are the vendor's
# spreadsheet headings, kept so the builder is untouched by this change — the
# source moves, the schema does not.
COLUMNS = ["Issuer", "Issuer Type", "County", "Elect. Date", "Prop. Number",
           "Result", "$ Amount", "Purpose", "Purpose Description",
           "Votes For", "Votes Against", "Source"]

FROM_SOCRATA = {
    "Issuer": "governmentname",
    "Issuer Type": "governmenttype",
    "County": "county",
    "Prop. Number": "propnumber",
    "Result": "result",
    "$ Amount": "amount",
    "Purpose": "purpose",
    "Purpose Description": "purposedescription",
    "Votes For": "votesfor",
    "Votes Against": "votesagainst",
    "Source": "source",
}

# Excel's day-zero. `build_bond_data.load()` parses the date column with
# origin="1899-12-30", because the vendor's file stored dates as Excel serials.
# Writing serials keeps that parser correct rather than quietly changing the
# meaning of the column under it.
EXCEL_EPOCH = dt.date(1899, 12, 30)

# A floor, not a target. The state's file held 5,059 ISD propositions when this
# was written; anything under this means the fetch truncated or the dataset
# moved, and publishing that would silently delete history.
MIN_ISD_ROWS = 4600


def fetch_all(where: str) -> list[dict]:
    """Page through Socrata until it stops giving us rows.

    Socrata caps a single response, so the offset walk is required rather than
    optional; asking for everything at once returns a truncated file with no
    error, which is exactly the failure this script exists to prevent.
    """
    ctx = ssl.create_default_context()
    out: list[dict] = []
    offset = 0
    while True:
        url = ENDPOINT + "?" + urllib.parse.urlencode({
            "$where": where, "$order": ":id", "$limit": PAGE, "$offset": offset})
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                page = json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Socrata returned HTTP {e.code} at offset {offset}: {url}")
        except Exception as e:  # noqa: BLE001 — any transport failure is fatal here
            raise SystemExit(f"could not reach {ENDPOINT}: {type(e).__name__}: {e}")
        out.extend(page)
        if len(page) < PAGE:
            return out
        offset += PAGE


def excel_serial(iso: str) -> str:
    """'2024-05-04T00:00:00.000' -> the Excel serial the builder expects."""
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso[:10])
    return str((d - EXCEL_EPOCH).days)


def to_row(r: dict) -> dict:
    row = {k: (r.get(src) or "") for k, src in FROM_SOCRATA.items()}
    row["Elect. Date"] = excel_serial(r.get("electiondate") or "")
    return row


def summarise(rows: list[dict]) -> dict:
    """Describe a set of propositions the same way whichever file they came
    from, so old and new can be compared honestly. The vendor export has no
    `Source` column and some unparseable date cells; both are tolerated here
    precisely because the point is to measure what changes."""
    decided = [r for r in rows if (r.get("Result") or "").strip() in ("Carried", "Defeated")]
    yrs = []
    for r in rows:
        v = (r.get("Elect. Date") or "").strip()
        if v.lstrip("-").isdigit():
            yrs.append(dt.date.fromordinal(EXCEL_EPOCH.toordinal() + int(v)).year)
    return {
        "rows": len(rows),
        "decided": len(decided),
        "issuers": len({(r.get("Issuer") or "").strip().upper() for r in rows}),
        "first_year": min(yrs) if yrs else None,
        "last_year": max(yrs) if yrs else None,
        "by_result": dict(Counter((r.get("Result") or "").strip() for r in rows)),
        "by_source": dict(Counter((r.get("Source") or "").strip() or "unstated"
                                  for r in rows)),
    }


def read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        # The vendor export carried Subtotal/Grand Total/blank rows. Keep only
        # what is actually a proposition so the comparison is like for like.
        return [r for r in csv.DictReader(fh)
                if (r.get("Issuer Type") or "").strip() == ISD]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data/texas_bond_elections.csv")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and report the difference, write nothing")
    args = ap.parse_args()

    print(f"fetching school bond elections from the Texas Bond Review Board\n  {LANDING}")
    raw = fetch_all(f"governmenttype='{ISD}'")
    rows = [to_row(r) for r in raw]
    rows.sort(key=lambda r: (r["Issuer"].upper(), r["Elect. Date"] or "0",
                             str(r["Prop. Number"])))

    now = summarise(rows)
    if now["rows"] < MIN_ISD_ROWS:
        raise SystemExit(
            f"refusing to write: got {now['rows']} ISD propositions, expected at "
            f"least {MIN_ISD_ROWS}. The fetch truncated or the dataset moved.")

    was = summarise(read_existing(args.out)) if args.out.exists() else None

    print(f"\n  propositions   {now['rows']:>6,}"
          + (f"   (was {was['rows']:,}, {now['rows'] - was['rows']:+,})" if was else ""))
    print(f"  decided        {now['decided']:>6,}"
          + (f"   (was {was['decided']:,}, {now['decided'] - was['decided']:+,})" if was else ""))
    print(f"  districts      {now['issuers']:>6,}"
          + (f"   (was {was['issuers']:,}, {now['issuers'] - was['issuers']:+,})" if was else ""))
    print(f"  years          {now['first_year']}–{now['last_year']}"
          + (f"   (was {was['first_year']}–{was['last_year']})" if was else ""))
    print("\n  per-row provenance, as the Board states it:")
    for k, v in sorted(now["by_source"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<10}{v:>6,}")

    if args.dry_run:
        print("\ndry run — nothing written")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {args.out.relative_to(ROOT)}  ({args.out.stat().st_size:,} bytes)")
    print("next: python scripts/build_bond_data.py && python scripts/audit_bond_match.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

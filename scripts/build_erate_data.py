"""Build static/erate_data.json — federal E-Rate money, per district.

E-Rate discounts school internet and telecom, paid by USAC mostly straight
to vendors — money that buys districts connectivity and largely never
appears in a district's PEIMS books. Roughly a quarter of a billion
dollars a year flows to Texas this way, and this is the only layer on the
site that can see it.

THE RULE (learned by nearly publishing a false finding): only FRNs with
status "Funded" are commitments. `funding_commitment_request` on a Pending
or Cancelled row is the amount ASKED, not granted — FY2018 still carries
$356M of stale Pending requests, and summing all statuses manufactures a
scandal-shaped utilization number that is actually a category error.
Funded-only, always; a test re-derives the statewide series under the same
rule from the raw file.

Attribution, stated not smoothed:
  * District-applicant BENs resolved to TEA numbers by the audited match
    (data/erate_district_match.csv — code, campus-prefix and name+county
    roads; disagreements refused). Unresolved BENs' money is counted in a
    named bucket, never dropped.
  * Consortium/school/library applicants are counted statewide and NEVER
    attributed to districts: a consortium's members benefit, but the
    record does not say which member got how much.
  * Disbursements lag: invoicing for a funding year can run for years
    (some FY2018 deadlines extend to 2026). A year is marked "open" while
    any of its Funded FRNs can still invoice; utilization on an open year
    is a floor, not a verdict.

Inputs (data/, gitignored): usac_erate_frns.csv, usac_entities_tx.csv,
erate_district_match.csv — written by scripts/ingest_erate.py.
Output: static/erate_data.json (committed).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, STATIC = ROOT / "data", ROOT / "static"

FRN_CSV = DATA / "usac_erate_frns.csv"
MATCH_CSV = DATA / "erate_district_match.csv"

FIRST_YEAR = 2017          # 2016 carries a single stray FRN


def money(v: str) -> float:
    return float(v) if v not in ("", None) else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(STATIC / "erate_data.json"))
    ap.add_argument("--today", default=None,
                    help="ISO date for the open-year rule. Default: the "
                         "recorded ingest vintage in freshness_vintages.json "
                         "— NOT the wall clock, so verify_artifacts' "
                         "rebuild-and-diff stays byte-identical between "
                         "ingests instead of drifting at midnight")
    args = ap.parse_args(argv)

    for p in (FRN_CSV, MATCH_CSV):
        if not p.exists():
            sys.exit(f"missing input: {p} — run scripts/ingest_erate.py first")

    today = args.today
    if not today:
        vint = json.loads(
            (ROOT / "scripts" / "freshness_vintages.json").read_text())
        today = vint["sources"]["usac_erate"]["vintage_utc"][:10]
    dt.date.fromisoformat(today)          # a bad date must fail loudly here

    ben_to_tea = {r["ben"]: r["district_number"]
                  for r in csv.DictReader(MATCH_CSV.open())
                  if r["district_number"]}
    match_rows = list(csv.DictReader(MATCH_CSV.open()))

    rows = [r for r in csv.DictReader(FRN_CSV.open())
            if r["form_471_frn_status_name"] == "Funded"
            and r["funding_year"].isdigit()
            and int(r["funding_year"]) >= FIRST_YEAR]

    tx_years: dict[int, dict] = defaultdict(
        lambda: {"committed": 0.0, "disbursed": 0.0, "frns": 0,
                 "open_frns": 0})
    buckets = defaultdict(lambda: {"committed": 0.0, "bens": set()})
    services = defaultdict(float)
    dist: dict[str, dict] = defaultdict(
        lambda: {"committed": 0.0, "disbursed": 0.0,
                 "years": defaultdict(lambda: [0.0, 0.0]),
                 "services": defaultdict(float)})

    for r in rows:
        y = int(r["funding_year"])
        c = money(r["funding_commitment_request"])
        d = money(r["total_authorized_disbursement"])
        ty = tx_years[y]
        ty["committed"] += c
        ty["disbursed"] += d
        ty["frns"] += 1
        inv = (r["last_date_to_invoice"] or "")[:10]
        if not inv or inv >= today:
            ty["open_frns"] += 1

        kind = r["organization_entity_type_name"]
        if kind == "School District":
            tea = ben_to_tea.get(r["ben"])
            if tea:
                rec = dist[tea]
                rec["committed"] += c
                rec["disbursed"] += d
                rec["years"][y][0] += c
                rec["years"][y][1] += d
                rec["services"][r["form_471_service_type_name"]] += c
                services[r["form_471_service_type_name"]] += c
                buckets["districts_attributed"]["committed"] += c
                buckets["districts_attributed"]["bens"].add(r["ben"])
            else:
                buckets["district_bens_unresolved"]["committed"] += c
                buckets["district_bens_unresolved"]["bens"].add(r["ben"])
        elif kind == "Consortium":
            buckets["consortia"]["committed"] += c
            buckets["consortia"]["bens"].add(r["ben"])
        else:
            buckets["schools_and_libraries"]["committed"] += c
            buckets["schools_and_libraries"]["bens"].add(r["ben"])

    # Accounting must balance to the cent before anything is written.
    total = sum(y["committed"] for y in tx_years.values())
    bucketed = sum(b["committed"] for b in buckets.values())
    assert abs(total - bucketed) < 1.0, (
        f"dollars leaked: years say {total:,.0f}, buckets say {bucketed:,.0f}")

    conflicts = sum(1 for r in match_rows if r["method"].startswith("CONFLICT"))
    unmatched = sum(1 for r in match_rows if r["method"] == "unmatched")
    matched = sum(1 for r in match_rows if r["district_number"])
    assert matched + conflicts + unmatched == len(match_rows)

    years_out = []
    for y in sorted(tx_years):
        t = tx_years[y]
        years_out.append({
            "year": y,
            "committed": round(t["committed"]),
            "disbursed": round(t["disbursed"]),
            "frns": t["frns"],
            # A year is open while ANY of its Funded FRNs can still invoice;
            # utilization on an open year is a floor, not a verdict.
            "invoicing_open": t["open_frns"] > 0,
            "drawn_pct": round(100 * t["disbursed"] / t["committed"], 1)
            if t["committed"] else None,
        })

    districts_out = {}
    for tea in sorted(dist):
        rec = dist[tea]
        top = max(rec["services"].items(), key=lambda kv: kv[1])
        years = [{"year": y, "committed": round(c), "disbursed": round(d)}
                 for y, (c, d) in sorted(rec["years"].items())]
        districts_out[tea] = {
            # Round once and derive the rest: the totals are the sum of the
            # displayed year figures, so a reader adding the column gets
            # exactly the total shown.
            "committed": sum(y["committed"] for y in years),
            "disbursed": sum(y["disbursed"] for y in years),
            "top_service": top[0],
            "years": years,
        }

    att = buckets["districts_attributed"]["committed"]
    unres = buckets["district_bens_unresolved"]["committed"]
    out = {
        "meta": {
            "first_year": FIRST_YEAR,
            "last_year": max(tx_years),
            "as_of": today,
            "funded_only": (
                "Sums cover FRNs with status 'Funded' ONLY. The dataset "
                "carries one row per FORM VERSION, so most funded requests "
                "also have a superseded Pending row whose "
                "funding_commitment_request is the amount ASKED, not "
                "granted — summing every status double-counts those and "
                "adds never-granted requests, inflating a funding year by "
                "hundreds of millions. No FRN carries two Funded rows "
                "(verified at ingest)."),
            "match": {
                "district_bens": len(match_rows),
                "matched": matched,
                "conflicts_refused": conflicts,
                "unmatched": unmatched,
                "dollars_attributed_pct": round(100 * att / (att + unres), 1),
            },
            "limits": [
                "E-Rate discounts are mostly paid by USAC straight to "
                "vendors, so this money buys a district connectivity "
                "without appearing as district spending in TEA's books — "
                "it is not comparable to, and never mixed with, the PEIMS "
                "figures elsewhere on this site.",
                "Consortium applications are counted statewide and never "
                "attributed to member districts: the record does not say "
                "which member received how much. A district with no record "
                "here may still receive service through a consortium.",
                "Disbursement lags commitment by design — invoicing for a "
                "funding year can run for years. A year marked "
                "invoicing_open has money still being drawn; its drawn "
                "percentage is a floor, not a finding.",
                "The applicant-to-district match resolves "
                "USAC billed-entity numbers to TEA numbers by state code, "
                "campus-code prefix and audited name+county; where two "
                "roads disagree the entity is refused rather than guessed. "
                "Charter NETWORKS spanning several TEA districts under one "
                "applicant number are counted in the unresolved bucket, "
                "not misassigned to one of their districts.",
                "Amounts are in the dollars of their own year and are not "
                "inflation-adjusted.",
            ],
        },
        "texas": {
            "years": years_out,
            "buckets": {
                k: {"committed": round(v["committed"]), "bens": len(v["bens"])}
                for k, v in sorted(buckets.items())
            },
            "service_types": [
                {"type": k, "committed": round(v)}
                for k, v in sorted(services.items(), key=lambda kv: -kv[1])
            ],
        },
        "districts": districts_out,
    }

    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out} — {len(districts_out)} districts, "
          f"{FIRST_YEAR}-{max(tx_years)}, "
          f"{out['meta']['match']['dollars_attributed_pct']}% of "
          f"district-applicant dollars attributed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

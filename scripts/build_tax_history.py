#!/usr/bin/env python3
"""What a district's tax rate has actually done, and why a bill moved.

The economics layer publishes ONE year of tax rates per district. So the site
could say what you pay now and could not say whether it had gone up — which is
the question people actually arrive with, and the one they ask their board.

The rates were already here: `scripts/ingest_tea_property.py` writes
`data/tea_property.csv` with `mo_rate`, `is_rate` and `taxable_value_roll` per
district per year, 2009 onward, and only the latest row was ever read.

The useful part is the decomposition. A school tax bill is rate x value, so a
bill can rise with the rate untouched — which is exactly what has happened
across most of Texas, and exactly what a rate-only answer hides. Every district
here gets both, separately, so "my taxes went up" resolves into which of the two
moved.

Two rules:

**A rate is only compared with a rate the same district actually reported.**
Districts appear and disappear from the Comptroller's file; a first-to-last
change computed across a gap is not a change.

**The bill is on a FIXED $300,000 home, and says so.** It is not anyone's
actual bill — no appraisal roll is involved and homestead exemptions are not
modelled. It is the same house priced under each year's rate, which is the only
way to show what the RATE did without an appraisal district's data.

Usage:
    python scripts/build_tax_history.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

HOME_VALUE = 300_000       # the same house every year, so only the rate moves
MIN_YEARS = 5              # below this a "trend" is two points and a straight line


def load(csv: Path) -> pd.DataFrame:
    d = pd.read_csv(csv, dtype={"district_number": str}, low_memory=False)
    for c in ("mo_rate", "is_rate", "total_tax_rate", "taxable_value_roll",
              "fall_survey_enrollment", "wealth_per_student", "recapture_paid"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def series_for(g: pd.DataFrame) -> dict:
    g = g.sort_values("year")
    g = g[g.total_tax_rate.notna()]
    if g.empty:
        return {}
    years = [int(y) for y in g.year]
    return {
        "years": years,
        "total_rate": [round(float(v), 4) for v in g.total_tax_rate],
        "mo_rate": [None if pd.isna(v) else round(float(v), 4) for v in g.mo_rate],
        "is_rate": [None if pd.isna(v) else round(float(v), 4) for v in g.is_rate],
        # Bill on the SAME house each year. Rates are per $100 of value.
        "bill_on_fixed_home": [round(float(v) * HOME_VALUE / 100) for v in g.total_tax_rate],
        "taxable_value": [None if pd.isna(v) else int(v) for v in g.taxable_value_roll],
    }


def build(d: pd.DataFrame) -> dict:
    districts: dict[str, dict] = {}
    for dn, g in d.groupby("district_number"):
        s = series_for(g)
        if not s or len(s["years"]) < 2:
            continue
        first_i, last_i = 0, len(s["years"]) - 1
        r0, r1 = s["total_rate"][first_i], s["total_rate"][last_i]
        b0, b1 = s["bill_on_fixed_home"][first_i], s["bill_on_fixed_home"][last_i]
        v0, v1 = s["taxable_value"][first_i], s["taxable_value"][last_i]

        # The whole point: separate what the RATE did from what VALUES did.
        # A bill can rise with the rate falling, and usually has.
        value_change_pct = (round((v1 / v0 - 1) * 100, 1)
                            if v0 and v1 and v0 > 0 else None)
        rate_change_pct = round((r1 / r0 - 1) * 100, 1) if r0 else None
        if rate_change_pct is not None and value_change_pct is not None:
            if rate_change_pct < -1 and value_change_pct > 1:
                reading = ("The rate came down while taxable values rose. A bill "
                           "that went up here did so because the property was "
                           "valued higher, not because the district raised its rate.")
            elif rate_change_pct > 1 and value_change_pct > 1:
                reading = ("Both the rate and taxable values rose, so a bill here "
                           "rose for both reasons.")
            elif rate_change_pct > 1:
                reading = "The rate rose while taxable values did not."
            else:
                reading = ("Neither the rate nor taxable values moved much over "
                           "this period.")
        else:
            reading = None

        districts[dn] = {
            "district_name": str(g.district_name.iloc[-1]),
            "first_year": s["years"][first_i],
            "last_year": s["years"][last_i],
            "years_reported": len(s["years"]),
            "series": s,
            "change": {
                "rate_first": r0, "rate_last": r1,
                "rate_change_pct": rate_change_pct,
                "bill_first": b0, "bill_last": b1,
                "bill_change": b1 - b0,
                "taxable_value_change_pct": value_change_pct,
                "reading": reading,
            },
            "home_value": HOME_VALUE,
            "short_series": len(s["years"]) < MIN_YEARS,
        }

    # Statewide, enrollment-weighted so it describes the average STUDENT's
    # district rather than the average district — 1,000 tiny districts would
    # otherwise outvote Houston.
    last = int(d.year[d.total_tax_rate.notna()].max())
    first = int(d.year[d.total_tax_rate.notna()].min())
    state = {}
    for y in range(first, last + 1):
        g = d[(d.year == y) & d.total_tax_rate.notna() & d.fall_survey_enrollment.notna()]
        if g.empty:
            continue
        w = g.fall_survey_enrollment
        state[y] = {
            "year": y,
            "districts": int(len(g)),
            "median_total_rate": round(float(g.total_tax_rate.median()), 4),
            "enrollment_weighted_rate": round(
                float((g.total_tax_rate * w).sum() / w.sum()), 4),
            "median_bill_on_fixed_home": round(
                float(g.total_tax_rate.median()) * HOME_VALUE / 100),
        }
    rows = [state[y] for y in sorted(state)]

    return {
        "meta": {
            "first_year": first,
            "last_year": last,
            "districts": len(districts),
            "home_value": HOME_VALUE,
            "source": "Texas Comptroller school district property values and "
                      "adopted tax rates, joined to TEA PEIMS enrollment",
            "publisher": "Texas Comptroller of Public Accounts / Texas Education Agency",
            "built_from": "data/tea_property.csv",
            "limits": [
                f"The bill is the same ${HOME_VALUE:,} home priced under each "
                f"year's rate. It is NOT anyone's actual bill: no appraisal roll "
                f"is used and homestead or over-65 exemptions are not modelled.",
                "Separating rate from value is the point. Across most of Texas "
                "the rate has FALLEN while bills rose, because taxable values "
                "rose faster. A rate-only answer gets that backwards.",
                "Rates are as adopted for the tax year and are matched to the "
                "fiscal year the finance file reports; a district that did not "
                "report in a year is skipped, never interpolated.",
                "Charters levy no property tax and have no row here at all.",
                "This layer labels a rate with the year the Comptroller adopted "
                "it. The economics card labels the SAME figure with the latest "
                "FINANCE year, because build_economics_data.py carries a "
                "district's last reported rate forward when the newest fiscal "
                "year has no adopted rate yet (rate_fallback, .groupby().last()). "
                "So a rate shown here as 2024 can appear there as 2025. Same "
                "number, two honest labels — stated here so a reader meeting "
                "both does not conclude one of them is wrong.",
                "The statewide line is enrollment-weighted as well as median, "
                "because 1,000 small districts would otherwise outvote Houston.",
            ],
        },
        "texas": {"years": rows},
        "districts": districts,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", default="data/tea_property.csv")
    ap.add_argument("--out", default="static/tax_history.json")
    args = ap.parse_args()

    csv = ROOT / args.property
    if not csv.exists():
        import sys
        print(f"missing input: {csv} — run scripts/ingest_tea_property.py --download "
              f"first", file=sys.stderr)
        return 1

    payload = build(load(csv))
    out = ROOT / args.out
    out.write_text(json.dumps(payload, separators=(",", ":")))
    m = payload["meta"]
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  {m['districts']:,} districts · {m['first_year']}-{m['last_year']}")
    rows = payload["texas"]["years"]
    if rows:
        a, b = rows[0], rows[-1]
        print(f"  statewide median rate {a['median_total_rate']:.4f} ({a['year']}) "
              f"-> {b['median_total_rate']:.4f} ({b['year']})")
        print(f"  bill on a ${m['home_value']:,} home: ${a['median_bill_on_fixed_home']:,}"
              f" -> ${b['median_bill_on_fixed_home']:,}")
    fell = sum(1 for r in payload["districts"].values()
               if (r["change"]["rate_change_pct"] or 0) < 0)
    print(f"  districts whose rate FELL over the window: {fell:,} of "
          f"{len(payload['districts']):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

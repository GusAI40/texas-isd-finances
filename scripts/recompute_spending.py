"""Re-derive the spending figures longhand, by a second road.

Same contract as scripts/recompute_revenue.py, same reason: the builder's
pandas pipeline computes each district's per-student spending figures and
the statewide headline, and a figure only its own builder vouches for is
unfalsifiable. This module recomputes them with nothing but the standard
library — `csv` and arithmetic, no pandas, no helper shared with the
builder — and the build REFUSES to write the artifact if any figure
disagrees.

What agreement proves: the pandas road — year selection, the division, the
filters. What it does NOT prove: both roads read prepare_data.py's cleaned
CSV and name the same truncated columns, so a wrong TEA→CSV mapping would
be reproduced by both. That link is held by the SHA-256 in
tests/fixtures/provenance.json and by scripts/verify_sources.py. Never let
the prose claim more.

Covers:
  * per district — instruction, debt service and operating spending per
    student (the three real divisions on the allocation card; the card's
    total is COMPOSED from two rounded figures and its "everything else"
    is a subtraction, so neither is a division and neither gets one).
  * statewide — the front page's headline: the sum of
    all_funds_total_disbursements across districts reporting in the latest
    year, and that sum divided by summed enrollment. The filter matches
    the live endpoint's: enrollment > 0 and disbursements > 0.

    python scripts/recompute_spending.py                 # statewide + a few districts
    python scripts/recompute_spending.py --district 057905
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINANCE = ROOT / "data" / "texas_finance_clean.csv"

INSTR = "all_funds_instruction_transfer_expend_fct11_95"
DEBT = "all_funds_total_debt_service_expend_by_obj"
OPERATING = "all_funds_total_operate_expend_by_function"
DISBURSEMENTS = "all_funds_total_disbursements"
ENROLLMENT = "fall_survey_enrollment"


def _num(raw: str | None) -> float:
    """A blank cell is zero spending; a malformed one is not silently zero."""
    s = (raw or "").strip()
    if not s:
        return 0.0
    return float(s)


def recompute(finance: Path = FINANCE, year: int | None = None) -> dict:
    """Per-district spending components for `year` (default: latest in file).

    Returns {district_number: {instruction, debt, operating, enrollment}} —
    raw dollars and the enrollment to divide by, so the caller applies the
    same round() the page displays.
    """
    if year is None:
        with finance.open(newline="") as fh:
            year = max(int(r["year"]) for r in csv.DictReader(fh) if r["year"])
    out: dict[str, dict] = {}
    with finance.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["year"] != str(year):
                continue
            enrol = _num(r.get(ENROLLMENT))
            if enrol <= 0:
                continue
            out[r["district_number"]] = {
                "instruction": _num(r.get(INSTR)),
                "debt": _num(r.get(DEBT)),
                "operating": _num(r.get(OPERATING)),
                "enrollment": enrol,
            }
    return out


def statewide(finance: Path = FINANCE, year: int | None = None) -> dict:
    """The headline sum: total disbursements across districts reporting.

    Filter parity with the live /dollar/texas endpoint is the whole point:
    enrollment > 0 AND disbursements > 0, nothing else.
    """
    if year is None:
        with finance.open(newline="") as fh:
            year = max(int(r["year"]) for r in csv.DictReader(fh) if r["year"])
    total = enrol_sum = 0.0
    districts = 0
    with finance.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["year"] != str(year):
                continue
            enrol = _num(r.get(ENROLLMENT))
            spend = _num(r.get(DISBURSEMENTS))
            if enrol <= 0 or spend <= 0:
                continue
            districts += 1
            total += spend
            enrol_sum += enrol
    return {"year": year, "districts": districts,
            "total_disbursements": total, "enrollment": enrol_sum}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--district", default=None)
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args(argv)
    sw = statewide(year=args.year)
    print(f"statewide fiscal {sw['year']}: {sw['districts']} districts, "
          f"${sw['total_disbursements']:,.0f} total disbursements, "
          f"${sw['total_disbursements'] / sw['enrollment']:,.0f} per student "
          f"({sw['enrollment']:,.0f} students)")
    # statewide() has already resolved the latest year; reuse it so the CLI
    # default path does not scan the 18 MB file a second time just for max().
    rows = recompute(year=sw["year"])
    picks = [args.district] if args.district else list(rows)[:3]
    for num in picks:
        r = rows.get(num)
        if not r:
            print(f"{num}: not in year {sw['year']}")
            continue
        e = r["enrollment"]
        print(f"{num}: instruction {round(r['instruction'] / e):,}/student, "
              f"debt {round(r['debt'] / e):,}, operating {round(r['operating'] / e):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Re-derive the revenue figures longhand, by a second road.

Why a second implementation of arithmetic we already do
------------------------------------------------------
`scripts/build_economics_data.py` computes these numbers with pandas: index
joins, a latest-year selection, a merge with the property file to add recapture
back, deflators. Every one of those steps can be wrong in a way that leaves a
plausible number behind, and a plausible number is exactly what this site cannot
afford — it has already published figures that were reproducible, tested, and
wrong.

So this module recomputes the same four revenue totals with nothing but the
standard-library `csv` reader: no pandas, no dataframe, no shared helper, no
import from the builder.

Exactly what agreement here proves, and what it does not
-------------------------------------------------------
It catches: a year picked off the wrong axis, a merge that duplicated or dropped
rows, an index join that silently misaligned districts, the recapture add-back
applied to the wrong row or the wrong year, a units slip, and a builder edited
without being re-run.

It does NOT catch a mistake made UPSTREAM of both roads. Both read
`data/texas_finance_clean.csv`, which is `scripts/prepare_data.py`'s output, not
TEA's workbook — that script snake-cases and truncates column names to 60
characters for Postgres, and both roads name the same truncated columns. If the
wrong TEA column were mapped there, both roads would reproduce it identically
and agree.

That link is covered elsewhere, not here: `tests/fixtures/provenance.json`
carries a SHA-256 of the clean CSV so an upstream restatement cannot pass
unnoticed, `tests/test_provenance.py` re-derives every headline from it longhand,
and `scripts/verify_sources.py` asserts that what TEA's URL actually serves is
the product we say it is. The chain is: TEA workbook -> prepare_data -> clean CSV
(hashed) -> two independent roads -> artefact -> page.

And none of it can make TEA's filing right. Districts file PEIMS and it is
corrected for years afterwards.

Usage
-----
    python scripts/recompute_revenue.py                 # print a few districts
    python scripts/recompute_revenue.py --district 057905

The builder imports `recompute()`; `tests/test_lineage.py` imports it too and
checks it against figures added by hand from the published file.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

FINANCE = Path("data/texas_finance_clean.csv")
PROPERTY = Path("data/tea_property.csv")

# The exact columns, named once. These are prepare_data.py's snake-cased names,
# which is why agreeing with the builder does not prove the TEA->CSV mapping is
# right — see the docstring. TEA reports M&O revenue NET of recapture, so a
# district that sends money to the state looks less locally funded than it is;
# recapture is added back from the property file to get GROSS local collections.
M_O = "all_funds_local_tax_revenue_from_m_o"
I_S = "all_funds_local_property_taxes_from_i_s"
OTHER_LOCAL = "all_funds_other_local_intermediate_revenue"
STATE = "all_funds_state_revenue"
FEDERAL = "all_funds_federal_revenue"
ENROLLMENT = "fall_survey_enrollment"


def _num(raw: str | None) -> float:
    """A blank cell is zero revenue; a malformed one is not silently zero."""
    s = (raw or "").strip()
    if not s:
        return 0.0
    return float(s.replace(",", "").replace("$", ""))


def _recapture(path: Path, year: int) -> dict[str, float]:
    """What each district paid back to the state, for the given fiscal year."""
    out: dict[str, float] = {}
    if not path.exists():
        return out
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if int(_num(row.get("year"))) != year:
                continue
            num = (row.get("district_number") or "").strip()
            if num:
                out[num] = _num(row.get("recapture_paid"))
    return out


def recompute(finance: Path = FINANCE, property_file: Path = PROPERTY,
              year: int | None = None) -> dict[str, dict[str, float]]:
    """{district_number: {total, local, state, federal, enrollment, year}}.

    `year` defaults to the latest fiscal year present in the finance file. Rows
    with no enrolment are returned with enrollment 0 rather than dropped — the
    caller decides what to do about a district it cannot divide, and silently
    dropping it is how a denominator problem becomes invisible.
    """
    rows: list[dict[str, str]] = []
    with finance.open(newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    if not rows:
        raise SystemExit(f"{finance} is empty")

    years = {int(_num(r.get("year"))) for r in rows if (r.get("year") or "").strip()}
    target = year if year is not None else max(years)
    recap = _recapture(property_file, target)

    out: dict[str, dict[str, float]] = {}
    for row in rows:
        if int(_num(row.get("year"))) != target:
            continue
        num = (row.get("district_number") or "").strip()
        if not num:
            continue
        local = (_num(row.get(M_O)) + recap.get(num, 0.0)
                 + _num(row.get(I_S)) + _num(row.get(OTHER_LOCAL)))
        state, federal = _num(row.get(STATE)), _num(row.get(FEDERAL))
        out[num] = {
            "local": local, "state": state, "federal": federal,
            "total": local + state + federal,
            "enrollment": _num(row.get(ENROLLMENT)),
            "year": float(target),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--finance", type=Path, default=FINANCE)
    ap.add_argument("--property", type=Path, default=PROPERTY)
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--district", default=None, help="6-digit TEA number")
    args = ap.parse_args(argv)

    table = recompute(args.finance, args.property, args.year)
    wanted = [args.district] if args.district else sorted(table)[:5]
    for num in wanted:
        r = table.get(num)
        if r is None:
            print(f"{num}: not in the file for that year")
            continue
        enrol = r["enrollment"]
        per = f"${r['total'] / enrol:,.0f}/student" if enrol else "no enrolment"
        print(f"{num}  fiscal {int(r['year'])}  total ${r['total']:,.0f}  "
              f"enrolment {enrol:,.0f}  {per}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Ingest TEA's district STAAR files: results by subject and by student group.

What this adds that the Snapshot summary could not
--------------------------------------------------
The Snapshot gives one number per district per year. These files give 5
subjects x 27 student groups x 3 performance bars, which lets the portal stop
asking "how did this district do" and start asking the question that actually
matters: **how did this district do FOR THE STUDENTS IT SERVES?** A district
can post a respectable average and still be failing its poor children, and
until now we could not see that.

They also extend the outcome series a year past the Snapshot (SY 2024-25).

Two traps that this script is built to avoid
--------------------------------------------
1. "Approaches grade level" is not grade level. Statewide in SY 2024-25:
   74.2% reached Approaches, **46.4% reached Meets**, 17.5% Masters. Everything
   the portal published before this used Approaches — the most flattering of
   the three. All three bars are emitted here, and Meets is the default,
   because "meets grade level" is what a parent thinks they are being told.

2. **A narrow gap is not good news.** The correlation between a district's
   poor/non-poor gap and how well its poor students actually do is +0.055 —
   essentially nothing. The narrowest-gap districts average 34.9% Meets for
   poor students against a statewide 37.9%: their gaps are narrow because
   nobody does well. So the headline measure here is the LEVEL for
   economically disadvantaged students, benchmarked against poor students
   elsewhere, with the gap reported only as context. Ranking on the gap alone
   would tell a district that it is doing well when everyone in it is failing.

Source: TEA "District STAAR Performance, All Grades" (one file per school
year). Column names encode the dimensions:
    STAAR Performance, <subject>, SY <year>, <group>, <metric>

Output: data/staar_district_long.csv — one row per district-year-subject-group.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ID_COL = "6 Digit County District Number"
NAME_COL = "District Name"

SUBJECTS = ["All Subjects", "Reading/Language Arts", "Mathematics", "Science", "Social Studies"]
# The groups worth carrying. The source has 27; these are the ones that answer
# a question a reader actually has, and every one of them is a protected or
# policy-relevant population.
GROUPS = [
    "All Students", "Econ Disadv", "Non-Econ Disadv", "EB/EL (Current)",
    "Special Ed (Current)", "Non-Special Ed", "At Risk", "Gifted and Talented",
    "African American", "Hispanic", "White", "Asian", "Continuously Enrolled",
]
METRICS = {
    "% At Approaches GL Standard or Above": "pct_approaches",
    "% At Meets GL Standard or Above": "pct_meets",
    "% At Masters GL Standard": "pct_masters",
    "# of Tests": "tests",
}
# Below this many tests TEA's percentages are both noisy and disclosure-masked;
# a district-group cell built on a handful of children should not be published.
MIN_TESTS = 25


def parse(path: Path, year: int) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype={ID_COL: str}, low_memory=False)
    if ID_COL not in raw.columns:
        raise SystemExit(f"{path}: no '{ID_COL}' column — is this a district STAAR file?")
    raw["district_number"] = raw[ID_COL].astype(str).str.strip().str.zfill(6)

    rows = []
    for col in raw.columns:
        # "STAAR Performance, <subject>, SY <yr>, <group>, <metric>"
        m = re.match(r"^STAAR Performance, (.+?), SY ([\d\-]+), (.+?), (.+)$", col)
        if not m:
            continue
        subject, _sy, group, metric = m.groups()
        if subject not in SUBJECTS or group not in GROUPS or metric not in METRICS:
            continue
        rows.append(pd.DataFrame({
            "district_number": raw.district_number,
            "district_name": raw[NAME_COL],
            "year": year,
            "subject": subject,
            "group": group,
            "measure": METRICS[metric],
            "value": pd.to_numeric(raw[col], errors="coerce"),
        }))
    if not rows:
        raise SystemExit(f"{path}: no recognised STAAR columns")
    long = pd.concat(rows, ignore_index=True)
    wide = long.pivot_table(
        index=["district_number", "district_name", "year", "subject", "group"],
        columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    for c in ("pct_approaches", "pct_meets", "pct_masters", "tests"):
        if c not in wide:
            wide[c] = pd.NA
    # Suppress cells built on too few tests rather than publishing noise.
    thin = wide.tests.fillna(0) < MIN_TESTS
    wide.loc[thin, ["pct_approaches", "pct_meets", "pct_masters"]] = pd.NA
    wide["suppressed"] = thin
    return wide


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", nargs="+", type=Path,
                    default=[Path("data/staar_district_2024.csv"),
                             Path("data/staar_district_2025.csv")],
                    help="district STAAR CSVs; the fiscal year is read off the filename")
    ap.add_argument("--out", type=Path, default=Path("data/staar_district_long.csv"))
    args = ap.parse_args()

    parts = []
    for f in args.files:
        if not f.exists():
            print(f"missing {f}", file=sys.stderr)
            return 1
        m = re.search(r"(20\d\d)", f.name)
        if not m:
            print(f"{f}: no 4-digit year in the filename", file=sys.stderr)
            return 1
        year = int(m.group(1))
        part = parse(f, year)
        parts.append(part)
        print(f"  {f.name}: {part.district_number.nunique():,} districts, {len(part):,} rows")

    out = pd.concat(parts, ignore_index=True).sort_values(
        ["district_number", "year", "subject", "group"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    latest = out[(out.year == out.year.max()) & (out.subject == "All Subjects")]
    allstu = latest[latest.group == "All Students"]
    poor = latest[latest.group == "Econ Disadv"].set_index("district_number").pct_meets
    rich = latest[latest.group == "Non-Econ Disadv"].set_index("district_number").pct_meets
    gap = (rich - poor).dropna()
    print(f"\nwrote {args.out} — {len(out):,} rows, "
          f"{out.district_number.nunique():,} districts, years {sorted(out.year.unique())}")
    print(f"  suppressed cells (under {MIN_TESTS} tests): "
          f"{out.suppressed.sum():,} of {len(out):,} ({out.suppressed.mean()*100:.1f}%)")
    print(f"  statewide, all students: {allstu.pct_approaches.mean():.1f}% approaches, "
          f"{allstu.pct_meets.mean():.1f}% MEETS, {allstu.pct_masters.mean():.1f}% masters")
    print(f"  economically disadvantaged: {poor.mean():.1f}% meets   "
          f"non-disadvantaged: {rich.mean():.1f}%   median gap {gap.median():.1f} pts")
    print(f"  correlation(gap, how poor students actually do) = "
          f"{gap.corr(poor):+.3f}  <- why the gap alone is not the metric")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

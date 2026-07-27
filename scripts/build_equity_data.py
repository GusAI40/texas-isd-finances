"""Build the equity layer: how a district does for the students it actually serves.

A district average hides who it is failing. Two districts can post the same
number while one carries its poor students with it and the other does not.
These files let the portal ask the better question: **how do THIS district's
economically disadvantaged children do, compared with poor children
elsewhere?**

The trap this is built to avoid
-------------------------------
The obvious feature is "which districts close the achievement gap". It is
wrong, and measurably so: the correlation between a district's poor/non-poor
gap and how well its poor students actually do is about **zero**. Rank on the
gap and you surface districts that are merely average for poor children — the
30 narrowest-gap districts average 40.2% against 39.0% statewide — because a
gap narrows just as easily when the top falls as when the bottom rises. Faith
Family Academy posts 18% for poor students and 17% for everyone else: a
one-point gap and a disaster.

So the headline here is the LEVEL for economically disadvantaged students,
placed against poor students statewide. The gap ships too, clearly secondary,
because it answers a different and still-real question: whether a district
serves two populations differently under one roof.

Bars
----
TEA publishes three. "Approaches grade level" is the lowest and is not grade
level; "Meets" is. Everything here defaults to Meets, matching the rest of the
portal, with the other two available.

Input:  data/staar_district_long.csv (scripts/ingest_staar_district.py)
Output: static/equity_data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BAR = "pct_meets"
SUBJECT = "All Subjects"
# A district-group cell needs enough tests to mean anything; the ingest already
# suppresses below 25, and a percentile ranking needs a firmer floor than that.
MIN_TESTS = 100

GROUPS = {
    "poor": "Econ Disadv",
    "not_poor": "Non-Econ Disadv",
    "emergent_bilingual": "EB/EL (Current)",
    "special_ed": "Special Ed (Current)",
    "all": "All Students",
}


def pick(df: pd.DataFrame, group: str, subject: str = SUBJECT) -> pd.DataFrame:
    return df[(df.group == group) & (df.subject == subject)].set_index("district_number")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staar", type=Path, default=Path("data/staar_district_long.csv"))
    ap.add_argument("--out", type=Path, default=Path("static/equity_data.json"))
    args = ap.parse_args()
    if not args.staar.exists():
        print(f"missing {args.staar} — run scripts/ingest_staar_district.py first", file=sys.stderr)
        return 1

    d = pd.read_csv(args.staar, dtype={"district_number": str}, low_memory=False)
    year = int(d.year.max())
    cur = d[d.year == year]
    prev_year = int(sorted(d.year.unique())[-2]) if d.year.nunique() > 1 else None
    prev = d[d.year == prev_year] if prev_year else None

    frames = {k: pick(cur, g) for k, g in GROUPS.items()}
    poor, notpoor = frames["poor"], frames["not_poor"]

    # Rank districts on how their POOR students do, among districts with enough
    # of them to rank. This is the headline; the gap is not.
    rankable = poor[(poor.tests >= MIN_TESTS) & poor[BAR].notna()]
    pct_rank = rankable[BAR].rank(pct=True) * 100

    state = {
        "year": year,
        "poor_meets": round(float(rankable[BAR].mean()), 1),
        "not_poor_meets": round(float(notpoor[notpoor[BAR].notna()][BAR].mean()), 1),
        "all_meets": round(float(frames["all"][frames["all"][BAR].notna()][BAR].mean()), 1),
        "median_gap": round(float((notpoor[BAR] - poor[BAR]).dropna().median()), 1),
        "districts_ranked": int(len(rankable)),
    }
    # The evidence for not ranking on the gap — published, not just asserted.
    gap_all = (notpoor[BAR] - poor[BAR]).dropna()
    common = gap_all.index.intersection(rankable.index)
    state["gap_vs_level_correlation"] = round(
        float(np.corrcoef(gap_all[common], rankable.loc[common, BAR])[0, 1]), 3)
    narrow = gap_all[common].nsmallest(30).index
    state["narrowest_gap_districts_poor_meets"] = round(
        float(rankable.loc[narrow, BAR].mean()), 1)

    subj_state = {}
    for s in ("Reading/Language Arts", "Mathematics"):
        v = pick(cur, GROUPS["poor"], s)[BAR].dropna()
        subj_state[s] = round(float(v.mean()), 1)

    districts = {}
    for num, row in poor.iterrows():
        if pd.isna(row[BAR]) or row.tests < MIN_TESTS:
            continue
        np_row = notpoor.loc[num] if num in notpoor.index else None
        rec = {
            "district_number": num,
            "district_name": str(row.district_name),
            "year": year,
            "poor": {
                "meets": float(row[BAR]),
                "approaches": None if pd.isna(row.pct_approaches) else float(row.pct_approaches),
                "masters": None if pd.isna(row.pct_masters) else float(row.pct_masters),
                "tests": int(row.tests),
                "percentile": round(float(pct_rank.loc[num])),
            },
        }
        if np_row is not None and pd.notna(np_row[BAR]):
            rec["not_poor_meets"] = float(np_row[BAR])
            # Secondary by design: a gap without a level is not a verdict.
            rec["gap"] = round(float(np_row[BAR] - row[BAR]), 1)
        # subject split for poor students — maths and reading diverge sharply
        rec["poor_by_subject"] = {}
        for s, key in (("Reading/Language Arts", "reading"), ("Mathematics", "math")):
            sub = pick(cur, GROUPS["poor"], s)
            if num in sub.index and pd.notna(sub.loc[num, BAR]):
                rec["poor_by_subject"][key] = float(sub.loc[num, BAR])
        # other groups this district serves
        rec["other_groups"] = {}
        for key in ("emergent_bilingual", "special_ed"):
            f = frames[key]
            if num in f.index and pd.notna(f.loc[num, BAR]) and f.loc[num, "tests"] >= MIN_TESTS:
                rec["other_groups"][key] = {
                    "meets": float(f.loc[num, BAR]), "tests": int(f.loc[num, "tests"])}
        # movement since last year, for poor students
        if prev is not None:
            pp = pick(prev, GROUPS["poor"])
            if num in pp.index and pd.notna(pp.loc[num, BAR]):
                rec["poor_change"] = round(float(row[BAR] - pp.loc[num, BAR]), 1)
        districts[num] = rec

    # Who does best FOR poor students, at a size where it is not noise.
    best = rankable[rankable.tests >= 2000].nlargest(12, BAR)
    leaders = [{"district_number": i, "district_name": str(r.district_name),
                "poor_meets": float(r[BAR]), "tests": int(r.tests)}
               for i, r in best.iterrows()]

    payload = {
        "meta": {
            "year": year, "previous_year": prev_year, "bar": "Meets grade level",
            "min_tests": MIN_TESTS,
            "districts": len(districts),
            "limits": [
                "The headline is how economically disadvantaged students do, NOT the "
                "gap. The gap correlates about zero with how well poor students "
                f"actually do ({state['gap_vs_level_correlation']}): the 30 "
                "narrowest-gap districts average "
                f"{state['narrowest_gap_districts_poor_meets']}% for poor students against "
                f"{state['poor_meets']}% statewide, so ranking on the gap picks out "
                "districts that are merely average for poor children. A gap narrows "
                "just as easily when the top falls as when the bottom rises.",
                "Results are at TEA's Meets grade level bar, not the lower Approaches.",
                f"District-group cells with fewer than {MIN_TESTS} tests are not "
                "ranked; TEA's percentages there are noisy and disclosure-masked.",
                "'Economically disadvantaged' is TEA's category, driven by free and "
                "reduced-price meal eligibility, and it is a blunt proxy for family "
                "circumstance.",
            ],
        },
        "state": state,
        "state_by_subject": subj_state,
        "leaders": leaders,
        "districts": districts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {args.out} — {len(districts):,} districts, "
          f"{args.out.stat().st_size / 1024:,.0f} KB, SY {year}")
    print(f"  poor students statewide: {state['poor_meets']}% meets   "
          f"non-poor: {state['not_poor_meets']}%   median gap {state['median_gap']} pts")
    print(f"  correlation(gap, how poor students do) = {state['gap_vs_level_correlation']:+.3f} "
          f"— why the gap is not the headline")
    print(f"  poor students: reading {subj_state['Reading/Language Arts']}%, "
          f"maths {subj_state['Mathematics']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

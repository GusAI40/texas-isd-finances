"""Did the state takeover of Houston ISD change results?

In June 2023 the Texas Education Agency replaced Houston ISD's elected board
with appointed managers and installed a new superintendent. It is the largest
state intervention in American public education and the most argued-about
education story in Texas. Both sides quote Houston's own before-and-after
numbers, which cannot settle it: every Texas district was climbing out of the
same pandemic hole at the same time.

What this does instead is compare Houston with districts that were in the same
hole and were NOT taken over.

Design
------
Difference-in-differences against a comparison group chosen on PRE-treatment
traits only — at least 40,000 students and at least 60% economically
disadvantaged as of 2023 — so the comparison cannot be picked to flatter the
answer. TEA's "year" is the school year ending, so 2023 was tested in spring
2023, months before the managers arrived: 2023 is the last untreated year,
2024 is year one and 2025 is year two.

Three things could make a real-looking effect fake, and each is tested and
published rather than assumed away:

1. **Houston might already have been pulling ahead.** Pre-period slopes are
   compared; if they diverge, the design does not hold.
2. **A five-point swing might just be normal.** The same calculation is run
   for every district in Texas as a placebo, and Houston's rank reported.
3. **The student body might have changed.** If lower-scoring children left,
   the average rises with no child learning more. Enrolment and poverty share
   are tracked across the transition.

What this is NOT
----------------
One treated district. There is no meaningful p-value for a sample of one, and
none is offered — the placebo rank is the honest substitute. Two years is
short. And "the takeover" bundles a new board, a new superintendent, a new
curriculum, mass staff turnover and school closures; nothing here separates
them. This measures whether results moved, not which decision moved them, and
it is not a verdict on the policy.

Inputs:  data/snapshot_all.csv, data/staar_district_long.csv
Output:  static/takeover_data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HISD = "101912"
TAKEOVER_YEAR = 2023          # last year tested before the managers arrived
PRE = [2018, 2019, 2021, 2022, 2023]   # 2020: no STAAR administered
POST = [2024, 2025]
MIN_STUDENTS = 40_000
MIN_POOR = 60.0


def outcome_panel(snap: pd.DataFrame, staar: pd.DataFrame) -> pd.DataFrame:
    """One % meeting grade level per district-year, 2018-2025.

    Snapshot carries 2018-2024; the district STAAR file carries 2025. Both are
    TEA's Meets bar for all students, all subjects, so they splice.
    """
    a = snap[snap.test_all_meets.notna()][["district_number", "year", "test_all_meets"]]
    b = (staar[(staar.subject == "All Subjects") & (staar.group == "All Students")
               & (staar.year == 2025)][["district_number", "year", "pct_meets"]]
         .rename(columns={"pct_meets": "test_all_meets"}))
    both = pd.concat([a, b], ignore_index=True)
    return both.pivot_table(index="district_number", columns="year", values="test_all_meets")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=Path, default=Path("data/snapshot_all.csv"))
    ap.add_argument("--staar", type=Path, default=Path("data/staar_district_long.csv"))
    ap.add_argument("--out", type=Path, default=Path("static/takeover_data.json"))
    args = ap.parse_args()
    for p in (args.snapshot, args.staar):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1

    snap = pd.read_csv(args.snapshot, dtype={"district_number": str}, low_memory=False)
    staar = pd.read_csv(args.staar, dtype={"district_number": str}, low_memory=False)
    w = outcome_panel(snap, staar).dropna(subset=PRE + POST)

    traits = snap[snap.year == TAKEOVER_YEAR].set_index("district_number")[
        ["district_name", "students", "pct_econ_disadv"]]
    w = w.join(traits, how="inner")
    if HISD not in w.index:
        print("Houston ISD missing from the panel", file=sys.stderr)
        return 1

    pool = w[(w.students >= MIN_STUDENTS) & (w.pct_econ_disadv >= MIN_POOR) & (w.index != HISD)]

    def change(row):
        return row[POST].mean() - row[TAKEOVER_YEAR]

    h_change = float(change(w.loc[HISD]))
    p_change = pool.apply(change, axis=1)

    # --- threat 1: parallel pre-trends ---
    slope = lambda ys: float(np.polyfit(range(len(ys)), ys, 1)[0])  # noqa: E731
    h_slope = slope([float(w.loc[HISD, y]) for y in PRE])
    c_slope = slope([float(pool[y].mean()) for y in PRE])

    # --- threat 2: placebo across every district ---
    eff_all = w[POST].mean(axis=1) - w[TAKEOVER_YEAR]
    big = w[w.students >= MIN_STUDENTS]
    eff_big = big[POST].mean(axis=1) - big[TAKEOVER_YEAR]

    # --- threat 3: did the student body change? ---
    enrol = snap.pivot_table(index="district_number", columns="year", values="students")
    poor = snap.pivot_table(index="district_number", columns="year", values="pct_econ_disadv")

    def shift(idx):
        return {
            "enrolment_before": float(enrol.loc[idx, TAKEOVER_YEAR].mean()),
            "enrolment_after": float(enrol.loc[idx, 2024].mean()),
            "enrolment_change_pct": round(float(
                enrol.loc[idx, 2024].mean() / enrol.loc[idx, TAKEOVER_YEAR].mean() - 1) * 100, 1),
            "poor_before": round(float(poor.loc[idx, TAKEOVER_YEAR].mean()), 1),
            "poor_after": round(float(poor.loc[idx, 2024].mean()), 1),
        }

    # --- who the gains reached ---
    groups = {"All Students": "all", "Econ Disadv": "low income",
              "EB/EL (Current)": "learning English",
              "Special Ed (Current)": "special education",
              "African American": "African American", "Hispanic": "Hispanic"}
    by_group = []
    for g, label in groups.items():
        piv = (staar[(staar.subject == "All Subjects") & (staar.group == g)]
               .pivot_table(index="district_number", columns="year", values="pct_meets"))
        if 2024 not in piv or 2025 not in piv or HISD not in piv.index:
            continue
        d = (piv[2025] - piv[2024]).dropna()
        if HISD not in d.index:
            continue
        comp = d[d.index.isin(pool.index)]
        by_group.append({
            "group": label,
            "houston_change": round(float(d[HISD]), 1),
            "comparison_change": round(float(comp.mean()), 1),
            "difference": round(float(d[HISD] - comp.mean()), 1),
            "houston_2025": None if 2025 not in piv else float(piv.loc[HISD, 2025]),
        })

    payload = {
        "meta": {
            "district_number": HISD,
            "district_name": "Houston ISD",
            "event": "TEA replaced the elected board with appointed managers, June 2023",
            "last_untreated_year": TAKEOVER_YEAR,
            "post_years": POST,
            "comparison_rule": f"at least {MIN_STUDENTS:,} students and at least "
                               f"{MIN_POOR:.0f}% economically disadvantaged in "
                               f"{TAKEOVER_YEAR}, chosen on pre-takeover traits only",
            "comparison_n": int(len(pool)),
            "bar": "Meets grade level",
            "limits": [
                "One treated district. There is no meaningful p-value for a sample of "
                "one and none is claimed; the placebo rank across every Texas district "
                "is the honest substitute.",
                "Two years of results is short.",
                "'The takeover' bundles a new board, a new superintendent, a new "
                "curriculum, heavy staff turnover and school closures. This measures "
                "whether results moved, not which decision moved them.",
                "Houston lost more enrolment than the comparison districts across the "
                "transition. Its poverty share held steady, so the leavers were not "
                "disproportionately poor, but a composition effect cannot be excluded.",
            ],
        },
        "headline": {
            "houston_change": round(h_change, 1),
            "comparison_change": round(float(p_change.mean()), 1),
            "difference": round(h_change - float(p_change.mean()), 1),
            "houston_rank_in_pool": int(pd.concat([p_change, pd.Series({HISD: h_change})])
                                        .rank(ascending=False)[HISD]),
            "pool_size": int(len(pool) + 1),
        },
        "trajectory": [{"year": int(y), "houston": float(w.loc[HISD, y]),
                        "comparison": round(float(pool[y].mean()), 1),
                        "treated": bool(y in POST)} for y in PRE + POST],
        "parallel_trends": {
            "houston_pre_slope": round(h_slope, 2),
            "comparison_pre_slope": round(c_slope, 2),
            "holds": bool(abs(h_slope - c_slope) < 0.6),
        },
        "placebo": {
            "districts_tested": int(len(eff_all)),
            "houston_rank": int(eff_all.rank(ascending=False)[HISD]),
            "houston_percentile": round(float(eff_all.rank(pct=True, ascending=False)[HISD]) * 100, 1),
            "rank_among_large_districts": int(eff_big.rank(ascending=False)[HISD]),
            "large_districts": int(len(eff_big)),
        },
        "composition": {"houston": shift([HISD]), "comparison": shift(list(pool.index))},
        "by_group": by_group,
        "comparison_districts": [
            {"district_number": i, "district_name": str(pool.loc[i, "district_name"]),
             "students": int(pool.loc[i, "students"]), "change": round(float(v), 1)}
            for i, v in p_change.sort_values(ascending=False).items()],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    hd = payload["headline"]
    print(f"wrote {args.out} — {args.out.stat().st_size / 1024:,.0f} KB")
    print(f"  Houston {hd['houston_change']:+.1f} vs comparison {hd['comparison_change']:+.1f} "
          f"= {hd['difference']:+.1f} points, rank {hd['houston_rank_in_pool']} of {hd['pool_size']}")
    print(f"  parallel pre-trends: {'holds' if payload['parallel_trends']['holds'] else 'DOES NOT HOLD'}"
          f" ({h_slope:+.2f}/yr vs {c_slope:+.2f}/yr)")
    print(f"  placebo: rank {payload['placebo']['houston_rank']} of "
          f"{payload['placebo']['districts_tested']:,} statewide, "
          f"rank {payload['placebo']['rank_among_large_districts']} of "
          f"{payload['placebo']['large_districts']} large districts")
    back = [g for g in by_group if g["difference"] < 0]
    print(f"  groups that did WORSE than comparison: "
          f"{', '.join(g['group'] for g in back) if back else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

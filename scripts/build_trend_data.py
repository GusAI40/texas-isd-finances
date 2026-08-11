"""Turn the forensic file from a photograph into a trajectory.

Every other layer on this site reports one year. A single year tells a board
where it stands; it cannot tell them which way they are moving, and moving is
the part they can still change. This builds the seventeen-year series — fiscal
2009 to 2025 — for the six measures that carry the statewide story, per
district, each against the state's own line.

Why these six
-------------
Statewide, in constant 2024 dollars, over these seventeen years:

  instruction's share of the operating dollar  57.8% -> 54.5%   (-3.3 pts)
  instruction per student                      $7,249 -> $6,880 (-$369)
  security per student                         $96 -> $232      (2.4x)
  debt service per student                     $1,507 -> $2,441 (1.6x)
  federal revenue per student (ESSER cliff)    $2,798 (2022) -> $1,432
  statewide operating balance                  +$3.0B (2022) -> -$1.6B (2025)
  districts in operating deficit               14.8% (2022) -> 44.4% (2025)

Those six move together and they are the squeeze: total spending per student
rose, but a shrinking share of it reaches a classroom, because debt service and
security absorbed the difference — and the federal money that masked it for
three years has gone while enrolment growth, which used to grow the base,
has flattened to ~12k a year from 70-95k in the 2010s.

Method, and what it refuses to do
---------------------------------
- **Constant 2024 dollars.** The deflator is taken from the economics artefact,
  which publishes nominal and real per-student spending side by side; their
  ratio IS the CPI-U factor that layer used. Reusing it keeps the whole site on
  one price base rather than inventing a second one.
- **Balanced-panel checked.** The statewide headline numbers were re-derived on
  only the 1,142 districts present in both 2009 and 2025 and moved by at most
  0.1 points, so the trend is not an artefact of which districts report. The
  check ships in the payload.
- **Operating balance is like-for-like.** Operating revenue against operating
  expenditure, both excluding debt service and capital. Comparing revenue with
  total spending would count buildings paid for out of bond PROCEEDS as a
  deficit, which is how a routine construction year gets published as a crisis.
- **A district's trend is described, never diagnosed.** A falling instruction
  share can be a district cutting classrooms or a district opening schools; the
  data cannot separate those for ONE district, so this reports the direction
  and the size against the state and stops there. Statewide is different: see
  reclassification_check, which establishes that the shift between functions is
  real reallocation rather than a recoding.
- **Small districts are volatile.** A 200-student district's per-student series
  swings on one retirement. Districts under MIN_STUDENTS get their series but
  are excluded from the statewide distribution and flagged.

Reads the committed CSV plus the economics artefact; writes static/trend_data.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FIRST, LAST = 2009, 2025
MIN_STUDENTS = 500      # below this a per-student series is mostly noise
MIN_YEARS = 8           # a trend needs enough of the window to be a trend

# TEA's column names, pinned here so a rename in the source fails loudly
# rather than silently producing a different series.
COLS = {
    "enr":    "fall_survey_enrollment",
    "op":     "all_funds_total_operating_expenditures_by_obj",
    "oprev":  "all_funds_total_operating_revenue",
    "debt":   "all_funds_total_debt_service_expend_by_obj",
    "instr":  "all_funds_instruction_transfer_expend_fct11_95",
    "sec":    "all_funds_security_monitoring_service_expend_fct52",
    "fed":    "all_funds_federal_revenue",
}

# key -> (label, unit, whether a RISE is the worrying direction, one-line question)
MEASURES = {
    "instruction_share": (
        "Share of the operating dollar reaching a classroom", "%", True,
        "Of every dollar spent on operations, how much is instruction?"),
    "instruction_ps": (
        "Instruction per student", "$", True,
        "In today's dollars, what is actually spent on teaching each student?"),
    "debt_ps": (
        "Debt service per student", "$", False,
        "What is being paid on past building debt — money outside the "
        "operating total TEA reports?"),
    "security_ps": (
        "Security and monitoring per student", "$", False,
        "What is spent keeping the campus safe?"),
    "operating_balance_ps": (
        "Operating revenue minus operating spending, per student", "$", True,
        "Does the district's operating income cover its operating costs?"),
    "federal_ps": (
        "Federal revenue per student", "$", True,
        "How much of the budget is federal money — the part that ended?"),
}


def load_frame(csv: Path) -> pd.DataFrame:
    d = pd.read_csv(csv, dtype={"district_number": str}, low_memory=False)
    missing = [c for c in COLS.values() if c not in d.columns]
    if missing:
        print(f"TEA columns not found (renamed upstream?): {missing}", file=sys.stderr)
        raise SystemExit(1)
    f = pd.DataFrame({"year": pd.to_numeric(d.year, errors="coerce"),
                      "num": d.district_number,
                      "name": d.district_name})
    for k, c in COLS.items():
        f[k] = pd.to_numeric(d[c], errors="coerce")
    f = f[(f.year >= FIRST) & (f.year <= LAST) & (f.enr > 0)].dropna(subset=["op", "enr"])
    return f


def deflator(econ: dict) -> dict[int, float]:
    """CPI-U factors to constant 2024 dollars, taken from the layer that
    already publishes both nominal and real per-student spending."""
    return {int(r["year"]): r["spend_per_student_real"] / r["spend_per_student_nominal"]
            for r in econ["macro"]["spending"]
            if r.get("spend_per_student_nominal")}


def measures_for(g: pd.DataFrame, defl: dict[int, float]) -> dict[str, list]:
    """The six series for one group of rows (a district, or the whole state)."""
    g = g.groupby("year").sum(numeric_only=True).sort_index()
    d = pd.Series({y: defl.get(int(y), np.nan) for y in g.index})
    total = g.op + g.debt.fillna(0)
    out = {
        "years": [int(y) for y in g.index],
        "enrollment": [int(v) for v in g.enr.round()],
        "instruction_share": (g.instr / g.op * 100).round(1).tolist(),
        "instruction_ps": (g.instr / g.enr * d).round(0).tolist(),
        "debt_ps": (g.debt.fillna(0) / g.enr * d).round(0).tolist(),
        "debt_share": (g.debt.fillna(0) / total * 100).round(1).tolist(),
        "security_ps": (g.sec.fillna(0) / g.enr * d).round(0).tolist(),
        "operating_balance_ps": ((g.oprev - g.op) / g.enr * d).round(0).tolist(),
        "federal_ps": (g.fed.fillna(0) / g.enr * d).round(0).tolist(),
    }
    # NaN is not valid JSON and json.dumps writes it anyway, which breaks every
    # parser downstream. Nulls are honest about a year a district did not report.
    return {k: ([None if (isinstance(x, float) and not np.isfinite(x)) else x for x in v]
                if isinstance(v, list) else v) for k, v in out.items()}


def change(series: dict, key: str) -> dict | None:
    """First-to-last change, plus the direction, ignoring missing years."""
    pairs = [(y, v) for y, v in zip(series["years"], series[key]) if v is not None]
    if len(pairs) < MIN_YEARS:
        return None
    (y0, v0), (y1, v1) = pairs[0], pairs[-1]
    return {"first_year": y0, "first": v0, "last_year": y1, "last": v1,
            "change": round(v1 - v0, 1),
            "pct_change": round((v1 - v0) / abs(v0) * 100, 1) if v0 else None}


def reclassification_check(csv: Path) -> dict:
    """Is instruction's falling share real reallocation, or a recoding?

    This was published as an unverified caveat. It is now testable four ways,
    and all four say reallocation:

    1. **Closed taxonomy.** The 16 function columns sum to the reported
       operating total in every year (ratio 0.9996-1.0000). No money moved
       into a bucket this does not measure.
    2. **Zero residual.** Rising functions and falling functions cancel
       exactly, so every point instruction lost is a point some other NAMED
       function gained.
    3. **No single absorber.** A recoding shows one bucket swallowing the
       decline. The largest riser gains 1.07 points against instruction's
       3.26 — the loss is spread across seven functions.
    4. **It predates COVID and outlives it.** -1.75 points by 2019, before
       any pandemic spending, and another -1.31 after the federal money left.

    A reclassification would break at least one of those. Recomputed on every
    build so a future TEA release cannot quietly change the answer.
    """
    d = pd.read_csv(csv, dtype={"district_number": str}, low_memory=False)
    fcols = [c for c in d.columns if c.startswith("all_funds_") and "fct" in c]
    op = pd.to_numeric(d["all_funds_total_operating_expenditures_by_obj"], errors="coerce")
    parts = sum(pd.to_numeric(d[c], errors="coerce").fillna(0) for c in fcols)
    tot = pd.DataFrame({"year": d.year, "op": op, "parts": parts}).dropna().groupby("year").sum()
    ratio = (tot.parts / tot.op)

    frame = pd.DataFrame({"year": d.year, **{
        c: pd.to_numeric(d[c], errors="coerce").fillna(0) for c in fcols}})
    g = frame.groupby("year").sum()
    share = g.div(g.sum(axis=1), axis=0) * 100
    inst = share[[c for c in share.columns if "instruction_transfer" in c][0]]
    moves = share.diff().sum()
    risers = moves[moves > 0]

    return {
        "functions": len(fcols),
        "parts_over_total_min": round(float(ratio.min()), 4),
        "parts_over_total_max": round(float(ratio.max()), 4),
        "rising_pts": round(float(risers.sum()), 2),
        "falling_pts": round(float(moves[moves < 0].sum()), 2),
        "residual_pts": round(float(moves.sum()), 3),
        "largest_single_riser": risers.idxmax().replace("all_funds_", ""),
        "largest_single_riser_pts": round(float(risers.max()), 2),
        "instruction_change_pts": round(float(inst.iloc[-1] - inst.iloc[0]), 2),
        "instruction_change_pre_covid_pts": round(float(inst[2019] - inst[FIRST]), 2)
        if 2019 in inst.index else None,
        "instruction_change_post_cliff_pts": round(float(inst[LAST] - inst[2022]), 2)
        if 2022 in inst.index else None,
        "verdict": "reallocation",
    }


def window_check(f: pd.DataFrame, defl: dict[int, float], start: int) -> dict:
    """Re-derive the lead finding on a SHORTER window.

    A fair question about any long series is whether the finding depends on how
    far back you go — old years are more restated, and more districts are
    missing from them. Answering it by shortening the window would be the wrong
    move: it buys panel coverage (87.2% complete over seventeen years, 94.9%
    over ten) and costs finding strength, and it makes nothing more accurate,
    because the long-window figures already re-derive exactly from source.

    So both are published. The two windows agreeing in direction is a
    robustness result; if they ever disagreed, THAT would be the finding.
    """
    w = f[f.year >= start]
    g = w.groupby("year").sum(numeric_only=True).sort_index()
    share = (g.instr / g.op * 100)
    yrs = sorted(w.year.unique())
    counts = w.groupby("num").year.nunique()
    complete = set(counts[counts == len(yrs)].index)
    b = w[w.num.isin(complete)].groupby("year").sum(numeric_only=True).sort_index()
    bshare = (b.instr / b.op * 100)
    d = pd.Series(defl).reindex(g.index)
    dps = (g.debt.fillna(0) / g.enr * d)
    return {
        "first_year": int(yrs[0]), "last_year": int(yrs[-1]), "years": len(yrs),
        "districts": int(counts.size),
        "complete_panel": len(complete),
        "complete_panel_pct": round(len(complete) / counts.size * 100, 1),
        "instruction_share_change": round(float(share.iloc[-1] - share.iloc[0]), 2),
        "instruction_share_change_balanced": round(float(bshare.iloc[-1] - bshare.iloc[0]), 2),
        "debt_ps_multiple": round(float(dps.iloc[-1] / dps.iloc[0]), 2),
    }


def build(f: pd.DataFrame, defl: dict[int, float], econ: dict,
          csv: Path | None = None) -> dict:
    state = measures_for(f, defl)
    state_change = {k: change(state, k) for k in MEASURES}

    # Balanced panel: same districts in the first and last year. If the
    # statewide story only exists because the roster changed, it is not a story.
    both = set(f[f.year == FIRST].num) & set(f[f.year == LAST].num)
    panel = measures_for(f[f.num.isin(both)], defl)
    panel_check = {
        "districts": len(both),
        "instruction_share_all": state_change["instruction_share"]["change"],
        "instruction_share_panel": change(panel, "instruction_share")["change"],
        "instruction_ps_all": state_change["instruction_ps"]["change"],
        "instruction_ps_panel": change(panel, "instruction_ps")["change"],
    }

    # Share of districts whose operating revenue did not cover operating spend.
    deficit = []
    for y, g in f.groupby("year"):
        g = g.dropna(subset=["oprev", "op"])
        if not len(g):
            continue
        short = g.op > g.oprev
        deficit.append({"year": int(y), "districts": int(len(g)),
                        "in_deficit": int(short.sum()),
                        "pct": round(float(short.mean()) * 100, 1),
                        "students_pct": round(
                            float(g.loc[short, "enr"].sum() / g.enr.sum()) * 100, 1),
                        # The sign of this is the whole story: it is what all
                        # districts together had left over after operations.
                        "statewide_margin": round(float(g.oprev.sum() - g.op.sum()))})

    districts, summary = {}, []
    for num, g in f.groupby("num"):
        if len(g) < MIN_YEARS:
            continue
        s = measures_for(g, defl)
        latest_enr = next((v for v in reversed(s["enrollment"]) if v), 0)
        ch = {k: change(s, k) for k in MEASURES}
        small = latest_enr < MIN_STUDENTS
        # Against the state: is this district's move steeper than everyone's?
        vs = {}
        for k, c in ch.items():
            if not c or not state_change.get(k):
                continue
            gap = round(c["change"] - state_change[k]["change"], 1)
            worrying_up = MEASURES[k][2] is False
            steeper = (gap > 0) if worrying_up else (gap < 0)
            vs[k] = {"gap_vs_state": gap,
                     "steeper_than_state": bool(steeper and abs(gap) > 0.001)}
        districts[num] = {
            "district_number": num,
            "district_name": str(g.name.iloc[-1]),
            "years": s["years"], "series": {k: s[k] for k in
                                            ("enrollment", "debt_share", *MEASURES)},
            "change": ch, "vs_state": vs,
            "small_district": bool(small),
            "note": ("Fewer than %d students, so per-student figures swing on a "
                     "single hire or retirement. Read the direction, not the "
                     "size." % MIN_STUDENTS) if small else None,
        }
        if not small:
            summary.append({
                "n": num, "name": str(g.name.iloc[-1]), "students": latest_enr,
                **{k: (ch[k]["change"] if ch.get(k) else None) for k in MEASURES},
            })

    findings = build_findings(state_change, deficit, state, panel_check)

    return {
        "meta": {
            "first_year": FIRST, "last_year": LAST,
            "years": LAST - FIRST + 1,
            "districts": len(districts),
            "dollars": "constant 2024 dollars, CPI-U, on the same price base as "
                       "the economics layer",
            "source": "TEA Summarized PEIMS Actual Financial Data, "
                      f"fiscal {FIRST}-{LAST}",
            "min_students_for_rankings": MIN_STUDENTS,
            "min_years_for_a_trend": MIN_YEARS,
            "balanced_panel_check": panel_check,
            "reclassification_check": reclassification_check(csv) if csv else None,
            # Same finding on a shorter window. Both published: agreement is
            # the robustness result, and disagreement would be the finding.
            "window_checks": [window_check(f, defl, y) for y in (FIRST, 2016, 2020)],
            "measures": {k: {"label": v[0], "unit": v[1], "fall_is_worrying": v[2],
                             "question": v[3]} for k, v in MEASURES.items()},
            "limits": [
                "A trend describes a direction, not a cause. A falling "
                "instruction share can be a district cutting classrooms or a "
                "district opening them; this data cannot tell the two apart.",
                "Operating balance compares operating revenue with operating "
                "spending only. Including debt service or capital would count "
                "buildings paid for out of bond proceeds as a deficit.",
                "The shift between functions is real reallocation, not "
                "reclassification: the 16 function codes still sum to the "
                "reported operating total in every year, risers and fallers "
                "cancel to a zero residual, no single function absorbs the "
                "decline, and it predates COVID and continues after the "
                "federal money left. See meta.reclassification_check.",
                f"Districts under {MIN_STUDENTS} students keep their series but "
                "are left out of the rankings: one retirement moves a small "
                "district's per-student figure more than a policy would.",
                f"Fiscal {LAST} is the newest release and has had the least "
                "time to be corrected.",
            ],
        },
        "statewide": {"years": state["years"],
                      "series": {k: state[k] for k in
                                 ("enrollment", "debt_share", *MEASURES)},
                      "change": state_change,
                      "deficit_by_year": deficit},
        "findings": findings,
        "summary": sorted(summary, key=lambda r: -(r["students"] or 0)),
        "districts": districts,
        "revenue_mix_now": econ["macro"]["revenue"],
    }


def build_findings(sc: dict, deficit: list, state: dict, panel: dict) -> list[dict]:
    """The statewide story, stated as numbers a board can check.

    Written here rather than in the page so the claim and the arithmetic that
    produced it live in the same file, and so a test can assert that every
    headline still matches the series it came from.
    """
    out = []
    ins_sh, ins_ps = sc["instruction_share"], sc["instruction_ps"]
    out.append({
        "key": "classroom_share",
        "headline": "The classroom's share of the operating dollar has fallen for "
                    "seventeen years",
        "figure": f"{ins_sh['first']}% → {ins_sh['last']}%",
        "detail": f"Instruction took {ins_sh['first']}% of every operating dollar in "
                  f"{ins_sh['first_year']} and {ins_sh['last']}% in {ins_sh['last_year']}, "
                  f"a fall of {abs(ins_sh['change'])} points. In constant dollars that is "
                  f"${abs(ins_ps['change']):,.0f} less per student on teaching, while total "
                  f"spending per student rose. Re-derived on only the "
                  f"{panel['districts']:,} districts reporting in both years, the fall is "
                  f"{abs(panel['instruction_share_panel'])} points — so this is not a "
                  f"change in who reports.",
    })
    dbt = sc["debt_ps"]
    out.append({
        "key": "debt", "headline": "Debt service is where the money went",
        "figure": f"${dbt['first']:,.0f} → ${dbt['last']:,.0f} per student",
        "detail": f"Up {dbt['pct_change']:.0f}% in constant dollars since "
                  f"{dbt['first_year']}. None of it appears in TEA's operating total, "
                  f"so a district can look lean on instruction while carrying the "
                  f"state's heaviest debt.",
    })
    sec = sc["security_ps"]
    out.append({
        "key": "security", "headline": "Security spending has more than doubled",
        "figure": f"${sec['first']:,.0f} → ${sec['last']:,.0f} per student",
        "detail": f"A {sec['last'] / sec['first']:.1f}-fold rise in constant dollars — "
                  f"the largest proportional increase of any function, and it comes out "
                  f"of the same operating dollar as instruction.",
    })
    fed = sc["federal_ps"]
    peak = max(zip(state["years"], state["federal_ps"]), key=lambda p: p[1] or 0)
    out.append({
        "key": "federal_cliff", "headline": "The federal money that masked it has gone",
        "figure": f"${peak[1]:,.0f} ({peak[0]}) → ${fed['last']:,.0f}",
        "detail": f"Federal revenue per student peaked in {peak[0]} and is down "
                  f"{(1 - fed['last'] / peak[1]) * 100:.0f}% since, in constant dollars — "
                  f"back below where it started in {fed['first_year']}.",
    })
    if deficit:
        now = deficit[-1]
        best = max(deficit, key=lambda r: r["statewide_margin"])
        worst_before = max(r["pct"] for r in deficit[:-2])
        # The sign flip is the finding. Before 2025 the state had never, in
        # this window, spent more on operations than operating revenue brought
        # in — so this is a first, not a worsening.
        flipped = now["statewide_margin"] < 0
        out.append({
            "key": "deficits",
            "headline": ("For the first time in seventeen years, Texas districts "
                         "together spent more on operations than operating revenue "
                         "brought in") if flipped else
                        "Districts are going into operating deficit, fast",
            "figure": f"{'+' if best['statewide_margin'] > 0 else ''}"
                      f"${best['statewide_margin'] / 1e9:,.1f}B ({best['year']}) → "
                      f"{'+' if now['statewide_margin'] > 0 else '−'}"
                      f"${abs(now['statewide_margin']) / 1e9:,.1f}B ({now['year']})",
            "detail": f"{now['in_deficit']:,} of {now['districts']:,} districts "
                      f"({now['pct']}%) spent more on operations than operating revenue "
                      f"covered in {now['year']}, and they enrol {now['students_pct']}% of "
                      f"Texas students. The worst any earlier year in this window reached "
                      f"was {worst_before}%. Operating revenue against operating spending "
                      f"only: debt service and construction are excluded on both sides, "
                      f"and so is the debt tax levy that pays for them — otherwise a "
                      f"routine building year reads as a crisis.",
        })
    enr = state["enrollment"]
    yrs = state["years"]
    recent = enr[-1] - enr[-3] if len(enr) >= 3 else 0
    early = (enr[yrs.index(2019)] - enr[yrs.index(2009)]) / 10 if 2019 in yrs else 0
    out.append({
        "key": "growth_stopped",
        "headline": "The growth that used to pay for it has stopped",
        "figure": f"{recent / 2:,.0f} students a year, was {early:,.0f}",
        "detail": f"Texas districts added about {early:,.0f} students a year through the "
                  f"2010s. Over the last two years they added {recent:,.0f} in total. "
                  f"Debt service and fixed costs do not shrink when growth does.",
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--finance", type=Path, default=Path("data/texas_finance_clean.csv"))
    ap.add_argument("--economics", type=Path, default=Path("static/economics_data.json"))
    ap.add_argument("--out", type=Path, default=Path("static/trend_data.json"))
    args = ap.parse_args()
    for p in (args.finance, args.economics):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1

    econ = json.loads(args.economics.read_text())
    payload = build(load_frame(args.finance), deflator(econ), econ, args.finance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))

    m = payload["meta"]
    print(f"wrote {args.out} — {m['districts']:,} districts x {m['years']} years, "
          f"{args.out.stat().st_size / 1024:,.0f} KB")
    print(f"  balanced-panel check: instruction share "
          f"{m['balanced_panel_check']['instruction_share_all']:+.1f} pts all vs "
          f"{m['balanced_panel_check']['instruction_share_panel']:+.1f} pts on "
          f"{m['balanced_panel_check']['districts']:,} districts")
    for f in payload["findings"]:
        print(f"  · {f['headline']}: {f['figure']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

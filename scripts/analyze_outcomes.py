"""What does a school dollar actually buy?

Joins our PEIMS spending data to the TEA Snapshot district file (see
scripts/ingest_tea_snapshot.py) and asks the question neither dataset can
answer alone: once you account for who a district teaches, does spending more
show up in results — and which districts do better than their circumstances
predict?

READ THIS BEFORE QUOTING ANY NUMBER BELOW
-----------------------------------------
Everything here is an ASSOCIATION measured across districts. None of it is
causal. A district that spends more and scores lower is not evidence that
spending hurts; it is overwhelmingly evidence that districts serving harder-to-
serve students both spend more (they receive need-based state and federal
funding) and post lower raw scores. That confound is the single most abused
fact in Texas school-finance argument, which is exactly why the residual model
below controls for student need before ranking anybody.

"Beating expectations" here means: scoring above what a district's student
demographics alone predict. It is a starting question — who is worth studying —
never a verdict on quality, and never a ranking of teachers or schools.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Student-need predictors. Deliberately EXOGENOUS to district decisions: a
# district chooses its budget, it does not choose its poverty rate. Using
# spending as a predictor here would bake the thing we want to measure into
# the baseline.
NEED = ["pct_econ_disadv", "pct_emergent_bilingual", "pct_special_ed"]


def load(finance_csv: Path, snapshot_csv: Path) -> pd.DataFrame:
    fin = pd.read_csv(finance_csv, dtype={"district_number": str}, low_memory=False)
    snap = pd.read_csv(snapshot_csv, dtype={"district_number": str}, low_memory=False)
    fin["district_number"] = fin["district_number"].str.zfill(6)
    snap["district_number"] = snap["district_number"].str.zfill(6)

    spend = "all_funds_total_operate_expend_by_function"
    fin = fin[["district_number", "year", spend, "fall_survey_enrollment",
               "all_funds_total_operating_revenue"]].rename(
        columns={spend: "operating_spend", "fall_survey_enrollment": "enrollment",
                 "all_funds_total_operating_revenue": "operating_revenue"})
    df = snap.merge(fin, on=["district_number", "year"], how="inner")
    df = df[(df["enrollment"] > 0) & (df["operating_spend"] > 0)]
    df["spend_per_student"] = df["operating_spend"] / df["enrollment"]
    return df


def ols(X: np.ndarray, y: np.ndarray):
    """Least squares with an intercept. Returns (coefs incl. intercept, r2)."""
    A = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return coef, (1 - ss_res / ss_tot if ss_tot else 0.0), pred


def variance_decomposition(d: pd.DataFrame, outcome: str) -> dict:
    """How much of the spread in results tracks student need, and how much
    tracks money, once need is already accounted for?"""
    cols = NEED + ["spend_per_student", outcome]
    d = d[cols].dropna()
    if len(d) < 200:
        return {}
    y = d[outcome].to_numpy(float)
    need = d[NEED].to_numpy(float)
    spend = d[["spend_per_student"]].to_numpy(float)

    _, r2_need, pred_need = ols(need, y)
    _, r2_spend, _ = ols(spend, y)
    _, r2_both, _ = ols(np.column_stack([need, spend]), y)

    # What spending explains that need has NOT already explained.
    resid = y - pred_need
    _, r2_spend_resid, _ = ols(spend, resid)
    r = float(np.corrcoef(d["spend_per_student"], d[outcome])[0, 1])
    return {
        "n": int(len(d)),
        "r2_need_only": round(r2_need, 4),
        "r2_spend_only": round(r2_spend, 4),
        "r2_both": round(r2_both, 4),
        "r2_spend_after_need": round(r2_spend_resid, 4),
        "raw_corr_spend_outcome": round(r, 4),
    }


def expectation_residuals(d: pd.DataFrame, outcome: str, year: int) -> pd.DataFrame:
    """Score each district against what its student population predicts."""
    d = d[d["year"] == year].dropna(subset=NEED + [outcome, "spend_per_student"]).copy()
    if len(d) < 100:
        return pd.DataFrame()
    y = d[outcome].to_numpy(float)
    _, r2, pred = ols(d[NEED].to_numpy(float), y)
    d["expected"] = pred
    d["gap"] = y - pred
    d["_r2"] = r2
    # spending percentile among districts in the same year
    d["spend_pctile"] = d["spend_per_student"].rank(pct=True) * 100
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--finance", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", help="write findings JSON here")
    args = ap.parse_args()

    df = load(Path(args.finance), Path(args.snapshot))
    findings: dict = {"joined_district_years": int(len(df)),
                      "years": [int(df.year.min()), int(df.year.max())]}
    print(f"Joined {len(df):,} district-years, {df.year.min()}–{df.year.max()}\n")

    # ---- 1. what explains results: who you teach, or what you spend? ----
    print("=" * 72)
    print("1. WHAT EXPLAINS DIFFERENCES IN RESULTS BETWEEN DISTRICTS?")
    print("=" * 72)
    findings["variance"] = {}
    for outcome, label in [("test_all_approaches", "STAAR % at/above grade level"),
                           ("grad_rate_4yr", "4-year graduation rate"),
                           ("attendance_rate", "attendance rate")]:
        v = variance_decomposition(df, outcome)
        if not v:
            continue
        findings["variance"][outcome] = v
        print(f"\n{label}  (n={v['n']:,} district-years)")
        print(f"   student need alone explains      {v['r2_need_only']*100:5.1f}% of the variation")
        print(f"   spending alone explains          {v['r2_spend_only']*100:5.1f}%")
        print(f"   both together                    {v['r2_both']*100:5.1f}%")
        print(f"   spending ADDS, after need        {v['r2_spend_after_need']*100:5.1f}%")
        print(f"   raw correlation spend vs result  {v['raw_corr_spend_outcome']:+.3f}")

    # ---- 2. the equity question: does money follow property wealth? ----
    print("\n" + "=" * 72)
    print("2. DOES SPENDING TRACK LOCAL PROPERTY WEALTH?")
    print("=" * 72)
    eq = df.dropna(subset=["taxable_value_per_pupil", "spend_per_student", "pct_econ_disadv"])
    latest = eq[eq.year == eq.year.max()]
    if len(latest) > 100:
        q = pd.qcut(latest["taxable_value_per_pupil"], 5,
                    labels=["poorest 20%", "2nd", "middle", "4th", "richest 20%"])
        tbl = latest.groupby(q, observed=True).agg(
            districts=("district_number", "count"),
            median_value_per_pupil=("taxable_value_per_pupil", "median"),
            median_spend=("spend_per_student", "median"),
            median_econ_disadv=("pct_econ_disadv", "median"),
            median_teacher_pay=("avg_teacher_salary", "median"),
            median_turnover=("teacher_turnover_pct", "median"))
        print(f"\nBy local property wealth per pupil, fiscal {int(latest.year.max())}:\n")
        print(tbl.round(0).to_string())
        findings["equity_by_wealth_quintile"] = json.loads(
            tbl.round(2).reset_index().to_json(orient="records"))

    # ---- 3. teacher pay, turnover, and results ----
    print("\n" + "=" * 72)
    print("3. TEACHER PAY, TURNOVER, AND RESULTS")
    print("=" * 72)
    t = df.dropna(subset=["avg_teacher_salary", "teacher_turnover_pct"])
    if len(t) > 500:
        corrs = {
            "pay_vs_turnover": float(t["avg_teacher_salary"].corr(t["teacher_turnover_pct"])),
            "turnover_vs_econ_disadv": float(t["teacher_turnover_pct"].corr(t["pct_econ_disadv"])),
            "pay_vs_spend": float(t["avg_teacher_salary"].corr(t["spend_per_student"])),
        }
        tt = t.dropna(subset=["test_all_approaches"])
        if len(tt) > 500:
            corrs["turnover_vs_result"] = float(
                tt["teacher_turnover_pct"].corr(tt["test_all_approaches"]))
        findings["workforce_correlations"] = {k: round(v, 4) for k, v in corrs.items()}
        for k, v in corrs.items():
            print(f"   {k:28s} r = {v:+.3f}")

    # ---- 3b. which levers survive the control that flattened spending? ----
    # Spending looks unrelated to results largely because need dominates. The
    # fair test is the same for every lever: how much does it explain of what
    # need has NOT already explained?
    print("\n" + "=" * 72)
    print("3b. WHAT STILL PREDICTS RESULTS ONCE STUDENT NEED IS ACCOUNTED FOR?")
    print("=" * 72)
    outcome = "test_all_approaches"
    levers = {
        "teacher_turnover_pct": "teacher turnover rate",
        "teacher_avg_experience": "teacher average experience",
        "pct_teachers_new": "% teachers with <=5 yrs experience",
        "avg_teacher_salary": "average teacher salary",
        "students_per_teacher": "students per teacher",
        "pct_spend_instruction": "% of spending on instruction",
        "spend_per_student": "spending per student",
    }
    rows = []
    for col, label in levers.items():
        d = df[NEED + [col, outcome]].dropna()
        if len(d) < 500:
            continue
        y = d[outcome].to_numpy(float)
        _, _, pred = ols(d[NEED].to_numpy(float), y)
        resid = y - pred
        _, r2_add, _ = ols(d[[col]].to_numpy(float), resid)
        rows.append({"lever": label, "n": int(len(d)),
                     "raw_corr": round(float(d[col].corr(d[outcome])), 3),
                     "explains_after_need_pct": round(r2_add * 100, 2)})
    rows.sort(key=lambda r: -r["explains_after_need_pct"])
    findings["levers_after_need"] = rows
    print("\nOutcome: STAAR % at/above grade level. Each lever tested alone, against\n"
          "the part of the result that student need does NOT explain:\n")
    print(f"   {'lever':38s} {'raw r':>7s} {'explains after need':>21s}")
    for r in rows:
        print(f"   {r['lever']:38s} {r['raw_corr']:+7.3f} {r['explains_after_need_pct']:>19.2f}%")

    # ---- 4. the hidden treasures ----
    print("\n" + "=" * 72)
    print("4. DISTRICTS BEATING WHAT THEIR DEMOGRAPHICS PREDICT")
    print("=" * 72)
    yr = int(df[df.test_all_approaches.notna()].year.max())
    res = expectation_residuals(df, "test_all_approaches", yr)
    if not res.empty:
        r2 = float(res["_r2"].iloc[0])
        print(f"\nModel: student need predicts {r2*100:.1f}% of the STAAR spread "
              f"in {yr} across {len(res):,} districts.")
        # the treasures: beat expectations while spending BELOW the median
        thrifty = res[res.spend_pctile <= 50].nlargest(15, "gap")
        cols = ["district_name", "pct_econ_disadv", "spend_per_student",
                "spend_pctile", "test_all_approaches", "expected", "gap"]
        print(f"\nBeat expectations MOST while spending below the state median "
              f"({len(res[res.spend_pctile <= 50]):,} such districts):\n")
        print(thrifty[cols].round(1).to_string(index=False))
        findings["overperformers_below_median_spend"] = json.loads(
            thrifty[cols + ["district_number"]].round(2).to_json(orient="records"))
        findings["expectation_model"] = {"year": yr, "r2": round(r2, 4),
                                         "n": int(len(res)), "predictors": NEED}
        # how often does high spending coincide with beating expectations?
        hi = res[res.spend_pctile >= 75]["gap"].mean()
        lo = res[res.spend_pctile <= 25]["gap"].mean()
        print(f"\nMean gap vs expectation — top spending quartile: {hi:+.1f} pts, "
              f"bottom quartile: {lo:+.1f} pts")
        findings["gap_by_spend_quartile"] = {"top_quartile": round(float(hi), 2),
                                             "bottom_quartile": round(float(lo), 2)}

    if args.out:
        Path(args.out).write_text(json.dumps(findings, indent=2))
        print(f"\nFindings written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

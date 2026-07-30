"""Build the economics layer: what you pay, where it goes, what it buys.

The portal could already say where a district's money goes and how its students
did. It could not answer the four questions an actual taxpayer asks:

    What do I pay?          -> the bill on a real house, and how much leaves
    Where does it go?       -> teaching vs buildings vs debt, in real dollars
    What does it buy?       -> the measured return on each lever, with error bars
    Who does better?        -> named districts with my size and my student need
                               that beat expectations reliably, not once

Everything here is precomputed into one static JSON so the endpoints work with
no database, the same way outcomes_data.json does.

The economics, and why each number is here
------------------------------------------
MICRO (the household and the district)
  tax_price      What a household pays for education, per $1,000 of spending
                 per student. Two districts can spend the same and charge very
                 different prices for it, because the tax base differs.
  opportunity_cost
                 Debt service expressed in teacher-equivalents. "This district
                 spends the price of 41 teachers a year on buildings" is a real
                 trade-off; "$5.6M of debt service" is not legible to anyone.
  marginal_product
                 What another $1,000 per student actually bought, measured
                 within districts over time. This is the number that makes the
                 whole spending argument concrete, and it is ~zero.
  generational_debt
                 Debt principal outstanding per enrolled student — what today's
                 buildings obligate tomorrow's taxpayers to.

MACRO (the state system)
  real_spending  Per-student spending deflated to constant dollars. Nominal
                 spending always rises; the question is whether real spending
                 did.
  financing_mix  M&O (operating, state-compressed) vs I&S (debt, locally voted)
                 over 19 years. A shift from taxing to borrowing is a shift of
                 cost onto the future.
  incidence      Recapture as a transfer: dollars per student sent or received,
                 and whether the system is progressive with respect to student
                 need (it is only weakly so, which is the finding).
  efficiency     Results against spending, both residualised on student need —
                 the allocative-efficiency question. If the frontier is flat,
                 money is not the binding constraint.

Honest limits, stated in the payload itself
-------------------------------------------
- Every effect size is observational. Within-district first differences remove
  everything about a district that does not change, which is most of what
  confounds a cross-sectional comparison, but not time-varying confounders.
- TEA does not itemise facilities. "Debt service" is all buildings together;
  a stadium is not separable from a roof without district bond documents.
- Districts where our two independent estimates of the tax base disagree by
  more than 25% are flagged and their tax figures withheld rather than shown.

Inputs:  data/texas_finance_clean.csv, data/tea_property.csv,
         data/snapshot_all.csv (scripts/ingest_tea_snapshot.py)
Output:  static/economics_data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# CPI-U annual averages, US city average (BLS). Used to state every dollar in
# constant 2024 terms — nominal school spending rises every year regardless.
CPI = {2009: 214.5, 2010: 218.1, 2011: 224.9, 2012: 229.6, 2013: 233.0,
       2014: 236.7, 2015: 237.0, 2016: 240.0, 2017: 245.1, 2018: 251.1,
       2019: 255.7, 2020: 258.8, 2021: 271.0, 2022: 292.7, 2023: 304.7,
       2024: 313.7, 2025: 322.1}
BASE = CPI[2024]

# The house we quote the tax bill on. Any figure works; this one is close to
# the statewide median and is a round number a reader can rescale in their head.
HOME_VALUE = 300_000

NEED = ["pct_econ_disadv", "pct_emergent_bilingual", "pct_special_ed"]
# "Approaches grade level" is the LOWEST of TEA's three bars and the portal
# used to report it: 74.2% of Texas students reach Approaches, 46.5% reach
# Meets, 17.6% reach Masters. A parent told "74%" hears "at grade level", which
# Approaches is not. Everything here uses MEETS.
#
# This is not only a labelling change. Scoring districts on Approaches versus
# Meets moves 35 of the top 100 "reliably beats expectations" districts, so
# modelling one bar while displaying another would name outperformers on a
# measure the reader never sees. Meets costs five years of span (it begins in
# 2018) and costs nothing in reliability: split-half r = 0.913 against 0.910.
OUTCOME = "test_all_meets"


def title_case(name: str) -> str:
    """TEA ships names in all caps. str.title() turns ISD into Isd and McKinney
    into Mckinney, so the acronyms and the Mc- prefix are handled explicitly —
    the same rule the portal's JavaScript uses, so both agree."""
    keep = {"ISD", "CISD", "MSD", "CSD", "STEM", "II", "III"}
    out = []
    for w in str(name).split():
        if w.upper() in keep:
            out.append(w.upper())
        elif w.upper().startswith("MC") and len(w) > 2:
            out.append("Mc" + w[2:].capitalize())
        else:
            # hyphenated names are several words: Hurst-Euless-Bedford
            out.append("-".join(x.capitalize() for x in w.split("-")))
    return " ".join(out)


def real(series: pd.Series, years: pd.Series) -> pd.Series:
    return series * years.map(CPI).rdiv(BASE)


def ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def residualise(df: pd.DataFrame, col: str) -> pd.Series:
    """What's left of `col` after student need explains what it can.

    Recomputed per year — the relationship between need and results is not
    stable across a test-standard change, and using one pooled model would
    smear that into every district's score.
    """
    out = pd.Series(index=df.index, dtype=float)
    for _, g in df.groupby("year"):
        sub = g.dropna(subset=[col] + NEED)
        if len(sub) < 50:
            continue
        X = np.column_stack([np.ones(len(sub)), sub[NEED].to_numpy(float)])
        beta = ols(sub[col].to_numpy(float), X)
        out.loc[sub.index] = sub[col].to_numpy(float) - X @ beta
    return out


def panel_effects(snap: pd.DataFrame) -> dict:
    """Within-district first differences: what a change in a lever bought.

    Differences are taken over three years, within a district, and only where
    the test standard did not change in between — TEA switched from
    'phase-in satisfactory' to 'approaches grade level' in 2018 and the two are
    not comparable. Year effects absorb statewide shocks, COVID included.

    This is the number the whole spending argument turns on, so it is computed
    here rather than quoted from anywhere.
    """
    d = snap.sort_values(["district_number", "year"]).copy()
    for c in ("avg_teacher_salary", "operating_per_pupil"):
        d[c] = real(d[c], d.year)
    levers = ["teacher_turnover_pct", "avg_teacher_salary", "teacher_avg_experience",
              "students_per_teacher", "operating_per_pupil", "pct_spend_instruction"]
    cols = levers + NEED
    g = d.groupby("district_number")
    H = 3
    for c in [OUTCOME] + cols:
        d["D_" + c] = g[c].diff(H)
    d["prev_std"] = g["test_standard"].shift(H)
    d["ygap"] = g["year"].diff(H)
    p = d[(d.test_standard == d.prev_std) & (d.ygap == H)].dropna(
        subset=["D_" + OUTCOME] + ["D_" + c for c in cols])

    yr = pd.get_dummies(p.year.astype(str), drop_first=True).to_numpy(float)
    X = np.column_stack([np.ones(len(p)), p[["D_" + c for c in cols]].to_numpy(float), yr])
    y = p["D_" + OUTCOME].to_numpy(float)
    beta = ols(y, X)
    resid = y - X @ beta
    # Cluster-robust (by district) standard errors — district-years within a
    # district are anything but independent, and naive SEs would be far too
    # narrow to be honest about.
    XtX_inv = np.linalg.pinv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for _, idx in p.groupby("district_number").indices.items():
        Xg, ug = X[idx], resid[idx]
        s = Xg.T @ ug
        meat += np.outer(s, s)
    n_c = p.district_number.nunique()
    scale = n_c / max(n_c - 1, 1)
    se = np.sqrt(np.diag(XtX_inv @ meat @ XtX_inv) * scale)

    effects = {}
    for i, c in enumerate(cols, start=1):
        effects[c] = {"per_unit": round(float(beta[i]), 6),
                      "ci_low": round(float(beta[i] - 1.96 * se[i]), 6),
                      "ci_high": round(float(beta[i] + 1.96 * se[i]), 6)}
    ss = float(((y - y.mean()) ** 2).sum())
    return {"horizon_years": H, "n_windows": int(len(p)),
            "n_districts": int(p.district_number.nunique()),
            "r2": round(1 - float((resid ** 2).sum()) / ss, 4),
            "effects": effects}


def reliability(snap: pd.DataFrame) -> pd.DataFrame:
    """How reliably a district beats what its student need predicts.

    One year of test results is noisy, and ranking districts on a single year
    is how a portal ends up celebrating luck. Averaging the residual over many
    years separates the two: split-half correlation across odd and even years
    is +0.91, so what survives is a real, stable district property.
    """
    s = snap[snap.year >= 2013].copy()
    s["resid"] = residualise(s, OUTCOME)
    r = s.dropna(subset=["resid"]).groupby("district_number").agg(
        score=("resid", "mean"), years=("resid", "size"))
    r = r[r.years >= 6]

    wide = s.dropna(subset=["resid"]).pivot_table(
        index="district_number", columns="year", values="resid")
    odd = wide[[c for c in wide.columns if c % 2 == 1]].mean(axis=1)
    even = wide[[c for c in wide.columns if c % 2 == 0]].mean(axis=1)
    both = odd.dropna().index.intersection(even.dropna().index)
    r.attrs["split_half_r"] = round(float(np.corrcoef(odd[both], even[both])[0, 1]), 3)
    return r


def matched_peers(cur: pd.DataFrame, num: str, k: int = 5) -> list:
    """Districts with this district's size and student need that do better.

    Matching is on the things a superintendent cannot change — enrollment (log,
    because the distribution spans four orders of magnitude), poverty, and
    emergent-bilingual share — so what is left to compare is practice. Ranking
    the 60 nearest by reliability, not by a single year, is what makes the list
    a place to call rather than a leaderboard.
    """
    me = cur.loc[num]
    o = cur.drop(index=num)
    z = lambda s, v: (v - s.mean()) / s.std()  # noqa: E731
    ls = np.log(cur.students)
    dist = ((z(ls, np.log(o.students)) - z(ls, np.log(me.students))) ** 2
            + (z(cur.pov, o.pov) - z(cur.pov, me.pov)) ** 2
            + (z(cur.eb, o.eb) - z(cur.eb, me.eb)) ** 2)
    near = o.assign(dist=dist).nsmallest(60, "dist")
    best = near[near.score > me.score].nlargest(k, "score")
    return [{"district_number": i, "name": title_case(r["name"]),
             "students": int(r.students), "pct_poor": round(float(r.pov), 1),
             "beats_by": round(float(r.score), 1),
             "turnover": None if pd.isna(r.turn) else round(float(r.turn), 1),
             "spend_per_student": None if pd.isna(r.spend) else int(r.spend)}
            for i, r in best.iterrows()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--finance", type=Path, default=Path("data/texas_finance_clean.csv"))
    ap.add_argument("--property", type=Path, default=Path("data/tea_property.csv"))
    ap.add_argument("--snapshot", type=Path, default=Path("data/snapshot_all.csv"))
    ap.add_argument("--out", type=Path, default=Path("static/economics_data.json"))
    args = ap.parse_args()
    for p in (args.finance, args.property, args.snapshot):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1

    fin = pd.read_csv(args.finance, dtype={"district_number": str}, low_memory=False)
    prop = pd.read_csv(args.property, dtype={"district_number": str}, low_memory=False)
    snap = pd.read_csv(args.snapshot, dtype={"district_number": str}, low_memory=False)

    DEBT = "all_funds_total_debt_service_expend_by_obj"
    INSTR = "all_funds_instruction_transfer_expend_fct11_95"
    TOTAL = "all_funds_total_operate_expend_by_function"
    PAYROLL = "all_funds_total_payroll_expenditures"

    fin = fin[fin.fall_survey_enrollment > 0].copy()
    for c in (DEBT, INSTR, TOTAL, PAYROLL):
        fin[c + "_ps"] = fin[c] / fin.fall_survey_enrollment
        fin[c + "_ps_real"] = real(fin[c + "_ps"], fin.year)

    # ---------------- MACRO ----------------
    latest = int(fin.year.max())
    by_year = fin.groupby("year").apply(lambda g: pd.Series({
        "spend_per_student_nominal": np.average(g[TOTAL + "_ps"], weights=g.fall_survey_enrollment),
        "spend_per_student_real": np.average(g[TOTAL + "_ps_real"], weights=g.fall_survey_enrollment),
        "debt_per_student_real": np.average(g[DEBT + "_ps_real"], weights=g.fall_survey_enrollment),
        "instruction_per_student_real": np.average(g[INSTR + "_ps_real"], weights=g.fall_survey_enrollment),
        "students": float(g.fall_survey_enrollment.sum()),
    })).reset_index()

    rates = prop.dropna(subset=["mo_rate"]).groupby("year").agg(
        mo=("mo_rate", "median"), is_=("is_rate", "median")).reset_index()
    rates["total"] = rates.mo + rates.is_
    rates["debt_share_pct"] = (rates.is_ / rates.total * 100).round(1)

    recap = prop.groupby("year").recapture_paid.sum().reset_index()
    ever = prop.groupby("district_number").recapture_paid.sum()
    ever = ever[ever > 0].sort_values(ascending=False)

    # ---------------- per-district, latest year ----------------
    f = fin[fin.year == latest].set_index("district_number")
    p = prop[prop.year == latest].set_index("district_number")
    # the rate file lags a year; fall back to the most recent year a district has
    rate_fallback = (prop.dropna(subset=["mo_rate"]).sort_values("year")
                     .groupby("district_number").last())

    snap_cur = snap[snap.year >= 2022].groupby("district_number").agg(
        name=("district_name", "last"), students=("students", "mean"),
        pov=("pct_econ_disadv", "mean"), eb=("pct_emergent_bilingual", "mean"),
        turn=("teacher_turnover_pct", "mean"), spend=("operating_per_pupil", "mean"),
        salary=("avg_teacher_salary", "mean"))
    rel = reliability(snap)
    cur = snap_cur.join(rel[["score"]], how="inner").dropna(
        subset=["students", "pov", "eb", "score"])

    panel = panel_effects(snap)
    # A teacher-equivalent, for translating debt service into something legible.
    teacher_cost = float(snap[snap.year == snap.year.max()].avg_teacher_salary.median())

    districts = {}
    withheld = no_tax_jurisdiction = 0
    for num, row in f.iterrows():
        pr = p.loc[num] if num in p.index else None
        rf = rate_fallback.loc[num] if num in rate_fallback.index else None
        mo = pr.mo_rate if pr is not None and pd.notna(pr.get("mo_rate")) else (
            rf.mo_rate if rf is not None else np.nan)
        is_ = pr.is_rate if pr is not None and pd.notna(pr.get("is_rate")) else (
            rf.is_rate if rf is not None else np.nan)
        check = pr.value_check_pct if pr is not None else np.nan
        recapture = float(pr.recapture_paid) if pr is not None and pd.notna(pr.recapture_paid) else 0.0
        gross_mo = (float(row["all_funds_local_tax_revenue_from_m_o"]) + recapture)

        tax = None
        # Two different reasons a district has no tax figures, and they must not
        # be conflated: a charter levies no property tax at all (absent by
        # nature), whereas a taxing district whose two independent tax-base
        # estimates disagree is a data-quality withholding. Reporting the first
        # as the second would overstate our own error rate sixfold.
        no_jurisdiction = pd.isna(mo) or mo <= 0
        if no_jurisdiction:
            no_tax_jurisdiction += 1
        elif pd.notna(check) and abs(check) > 25:
            withheld += 1
        else:
            # Quote the bill from the RATE WE DISPLAY, not from full precision:
            # otherwise the reader multiplies 0.8770 by their home value and
            # gets a different answer from the one on the page.
            total_rate = round(float(mo) + float(is_ or 0), 4)
            bill = HOME_VALUE / 100 * total_rate
            leaves = bill * (float(mo) / total_rate) * (recapture / gross_mo if gross_mo > 0 else 0)
            tax = {
                "mo_rate": round(float(mo), 4), "is_rate": round(float(is_ or 0), 4),
                "total_rate": total_rate,
                "bill_on_home": round(bill),
                "leaves_district": round(leaves),
                "home_value": HOME_VALUE,
                # tax price: what a household pays per $1,000 of spending per student
                "tax_price": round(bill / (row[TOTAL + "_ps"] / 1000), 2)
                if row[TOTAL + "_ps"] > 0 else None,
            }

        debt_ps, instr_ps = float(row[DEBT + "_ps"]), float(row[INSTR + "_ps"])
        _instr, _debt = round(instr_ps), round(debt_ps)
        _operating = round(float(row[TOTAL + "_ps"]))
        entry = {
            "district_number": num,
            "district_name": title_case(row.district_name),
            "year": latest,
            "students": int(row.fall_survey_enrollment),
            "tax": tax,
            # Debt service sits OUTSIDE 'total operating expenditure by function' in
            # TEA's structure, so the three parts must be composed, not carved out
            # of the operating total — doing the latter yields a negative residual
            # for any district with heavy debt.
            # Round ONCE and derive the rest, so the parts add up on screen.
            # Rounding each component independently left a quarter of districts
            # off by a dollar — arithmetically explainable, and still the first
            # thing a superintendent notices when they add the column.
            "allocation": {
                "instruction_per_student": _instr,
                "debt_per_student": _debt,
                "other_operating_per_student": _operating - _instr,
                "operating_per_student": _operating,
                "total_per_student": _operating + _debt,
                "payroll_per_student": round(float(row[PAYROLL + "_ps"])),
                "cents_on_debt_per_dollar_taught": round(debt_ps / instr_ps * 100)
                if instr_ps > 0 else None,
                # the trade-off, in units a school board actually decides in
                "teachers_equivalent_of_debt": round(
                    debt_ps * row.fall_survey_enrollment / teacher_cost)
                if teacher_cost > 0 else None,
            },
            "recapture": {"paid": round(recapture),
                          "per_student": round(recapture / row.fall_survey_enrollment),
                          "share_of_local_mo": round(recapture / gross_mo, 4) if gross_mo > 0 else 0.0},
        }
        if num in cur.index:
            c = cur.loc[num]
            entry["own"] = {
                "pct_poor": None if pd.isna(c.pov) else round(float(c.pov), 1),
                "turnover": None if pd.isna(c.turn) else round(float(c.turn), 1),
            }
            entry["reliability"] = {
                "score": round(float(c.score), 1),
                "years_measured": int(rel.loc[num, "years"]),
                "percentile": round(float((cur.score < c.score).mean() * 100)),
            }
            entry["who_does_better"] = matched_peers(cur, num)
        districts[num] = entry

    payload = {
        "meta": {
            "year": latest,
            "home_value": HOME_VALUE,
            "teacher_cost": round(teacher_cost),
            "districts": len(districts),
            "tax_figures_withheld_qa": withheld,
            "no_tax_jurisdiction": no_tax_jurisdiction,
            "split_half_reliability": rel.attrs["split_half_r"],
            "dollars": "constant 2024 dollars where marked real; CPI-U annual average",
            "sources": [
                "TEA Summarized PEIMS Actual Financial Data, fiscal 2009-2025",
                "TEA/Comptroller certified property values, tax years 2015-2025",
                "TEA school district adopted tax rates, 2005-06 to 2023-24",
                "TEA recapture paid by district, fiscal 1994-2026",
                "TEA Snapshot district detail, 2009-2024",
            ],
            "limits": [
                "Effect sizes are observational. Within-district first differences "
                "remove everything about a district that does not change, but not "
                "confounders that move at the same time.",
                "TEA does not itemise facilities: debt service covers all buildings "
                "together, so a stadium cannot be separated from a roof without a "
                "district's own bond documents.",
                "Tax figures are withheld for districts where two independent "
                "estimates of the tax base disagree by more than 25%.",
            ],
        },
        "macro": {
            "spending": by_year.round(2).to_dict("records"),
            "tax_rates": rates.round(4).to_dict("records"),
            "recapture_by_year": recap.round(0).to_dict("records"),
            "recapture_concentration": {
                "districts_ever_paying": int(len(ever)),
                "total": round(float(ever.sum())),
                "top10_share": round(float(ever.head(10).sum() / ever.sum()), 3),
                "top25_share": round(float(ever.head(25).sum() / ever.sum()), 3),
                "top100_share": round(float(ever.head(100).sum() / ever.sum()), 3),
            },
        },
        "micro": {
            "marginal_product": panel,
            "note": "effects are the change in STAAR percent-approaches for a "
                    "one-unit change in the lever, within the same district over "
                    "three years, with year effects and district-clustered errors",
        },
        "districts": districts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out} — {len(districts):,} districts, {kb:,.0f} KB")
    print(f"  split-half reliability of the score: r={rel.attrs['split_half_r']:+.3f}")
    print(f"  tax figures withheld for QA: {withheld}   "
          f"charters with no tax jurisdiction: {no_tax_jurisdiction}")
    e = panel["effects"]
    print(f"  marginal product of $1,000/student: "
          f"{e['operating_per_pupil']['per_unit'] * 1000:+.3f} STAAR points "
          f"[{e['operating_per_pupil']['ci_low'] * 1000:+.3f}, "
          f"{e['operating_per_pupil']['ci_high'] * 1000:+.3f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

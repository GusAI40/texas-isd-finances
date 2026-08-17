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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recompute_revenue  # noqa: E402 — sibling script, path set above
import recompute_spending  # noqa: E402

# Named once, so the artefact says which file the second road actually read
# rather than describing it in prose that can drift from the code.
RECOMPUTED_FROM = ("data/texas_finance_clean.csv + data/tea_property.csv, "
                   "re-read longhand by scripts/recompute_revenue.py")
# The spending road reads one file fewer — its figures need no property data —
# so it carries its own provenance string rather than borrowing revenue's.
SPEND_RECOMPUTED_FROM = ("data/texas_finance_clean.csv, "
                         "re-read longhand by scripts/recompute_spending.py")

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

    # --- where the money comes FROM, not just where it goes ---
    LOC_MO = "all_funds_local_tax_revenue_from_m_o"
    LOC_IS = "all_funds_local_property_taxes_from_i_s"
    STATE = "all_funds_state_revenue"
    FEDERAL = "all_funds_federal_revenue"
    OTHER_LOC = "all_funds_other_local_intermediate_revenue"
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

    _rf = fin[fin.year == latest]
    _rl = (_rf[LOC_MO].sum() + _rf[LOC_IS].sum() + _rf[OTHER_LOC].sum()
           + prop[prop.year == latest].recapture_paid.sum())
    _rs, _rd = _rf[STATE].sum(), _rf[FEDERAL].sum()
    _rt = _rl + _rs + _rd
    _slp, _ssp = round(_rl / _rt * 100), round(_rs / _rt * 100)
    statewide_revenue = {"local_pct": _slp, "state_pct": _ssp,
                         "federal_pct": 100 - _slp - _ssp,
                         "local": float(_rl), "state": float(_rs), "federal": float(_rd)}

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

    # The independent re-derivation, computed once for every district before the
    # loop. See scripts/recompute_revenue.py for why it exists and what its
    # agreement does and does not prove.
    redone = recompute_revenue.recompute(args.finance, args.property, int(latest))
    redone_spend = recompute_spending.recompute(args.finance, int(latest))
    disagreements: list[str] = []
    unrecomputed: list[str] = []
    recomputed = 0

    # ---------------- the statewide headline, with its working ----------------
    # "Public schools spent $109.4 billion" is the first number on the site, and
    # it was the last without evidence. It is a SUM, not a division — the gate
    # reports arithmetic n/a for it — and the per-student companion divides that
    # sum by summed enrollment over the SAME districts. The filter must match
    # the live /dollar/texas endpoint's exactly: enrollment > 0 (already applied
    # to `fin`) and total disbursements > 0. `fin` is not refiltered globally
    # because every other figure in this artefact keeps the enrollment-only rule.
    DISB = "all_funds_total_disbursements"
    _swf = fin[(fin.year == latest) & (fin[DISB] > 0)]
    sw_total = float(_swf[DISB].sum())
    sw_enrol = float(_swf.fall_survey_enrollment.sum())
    sw_districts = int(len(_swf))
    sw_redo = recompute_spending.statewide(args.finance, int(latest))
    statewide_lineage = {
        "recomputed_from": SPEND_RECOMPUTED_FROM,
        "fiscal_year": int(latest),
        "source_id": "tea_peims",
        "measure_id": "spend_per_student",
        "source": "Texas Education Agency",
        "artifact": "economics_data.json",
        "districts": sw_districts,
        "filter": "fall survey enrollment > 0 and total disbursements > 0",
        "figures": {
            "statewide_total_spend": {
                "value": round(sw_total),
                "numerator": round(sw_total),
                # No denominator: a sum, so the gate's arithmetic check is n/a
                # by design rather than a division invented to fill the field.
                "formula": ("sum of all_funds_total_disbursements over districts "
                            "reporting enrollment and spending"),
                "denominator_type": "",
                "unit": "USD",
                "recomputed_value": round(sw_redo["total_disbursements"]),
            },
            "statewide_spend_per_student": {
                "value": round(sw_total / sw_enrol),
                "numerator": round(sw_total),
                "denominator": round(sw_enrol),
                "denominator_type": ("sum of fall survey enrollment over the "
                                     "same districts"),
                "formula": ("sum of all_funds_total_disbursements / sum of "
                            "fall survey enrollment"),
                "unit": "USD per student",
                "recomputed_value": round(
                    sw_redo["total_disbursements"] / sw_redo["enrollment"]),
            },
        },
    }
    for key, fig in statewide_lineage["figures"].items():
        recomputed += 1
        # These figures are sums (or a division of sums) of ~1,200 addends at
        # $1e11 scale: pandas sums pairwise, the second road sequentially, and
        # the two orders can legitimately differ in the last float bits. A $1
        # gap on the rounded values at an exact .5 boundary is summation
        # order, not a disagreement; anything larger is real and refuses the
        # build. Per-district figures stay exact — they are single cells, not
        # sums. (The gate's own _close() is relative and never trips on this.)
        if abs(fig["recomputed_value"] - fig["value"]) > 1:
            disagreements.append(f"statewide {key}: built {fig['value']}, "
                                 f"re-derived {fig['recomputed_value']}")
    if sw_districts != sw_redo["districts"]:
        disagreements.append(
            f"statewide district count: built {sw_districts}, "
            f"re-derived {sw_redo['districts']}")

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

        # revenue by source, per student, from gross local collections
        enrol = float(row.fall_survey_enrollment)
        _loc = gross_mo + float(row.get(LOC_IS, 0) or 0) + float(row.get(OTHER_LOC, 0) or 0)
        _st, _fed = float(row.get(STATE, 0) or 0), float(row.get(FEDERAL, 0) or 0)
        _tot = _loc + _st + _fed
        _revenue = None
        if _tot > 0 and enrol > 0:
            _lp, _sp = round(_loc / _tot * 100), round(_st / _tot * 100)
            _revenue = {
                "local_per_student": round(_loc / enrol),
                "state_per_student": round(_st / enrol),
                "federal_per_student": round(_fed / enrol),
                "total_per_student": round(_tot / enrol),
                # shares are forced to sum to 100 so the labels on the bar agree
                "local_pct": _lp, "state_pct": _sp, "federal_pct": 100 - _lp - _sp,
                "note": "local is gross property tax before recapture is deducted",
            }
            # Emit the EVIDENCE, not just the answer. Rounding away the
            # numerator and denominator is how a figure becomes unfalsifiable:
            # a reader can no longer tell $23,420 from a typo, and neither can
            # we. See src/lineage.py — this object is what the dashboard shows
            # when someone clicks the number, and what the district_lineage MCP
            # tool hands to somebody else's assistant.
            #
            # The denominator is named explicitly. "Per student" is not a
            # definition: this site already publishes two per-student figures
            # that legitimately disagree because one divides by enrolment and
            # the other by a different total.
            #
            # Only what VARIES is stored per district. The formula, the unit, the
            # name of the denominator and the source id are identical for all
            # 1,202 of them, so they live once in meta.lineage_templates below.
            # Emitting them per district doubled this artefact for no new fact —
            # and worse, it would let one district's copy of "the formula" drift
            # from another's, which is precisely the thing lineage exists to stop.
            #
            # `recomputed` is the SECOND road: scripts/recompute_revenue.py
            # re-reads TEA's own CSV with the standard-library csv module, no
            # pandas and no helper shared with this file. Comparing this
            # artefact against something derived from this artefact would prove
            # only that the generator ran — a mistake this repo shipped once and
            # stayed green through for weeks.
            _redo = redone.get(num) or {}
            _revenue["lineage"] = {
                "denominator": round(enrol),
                "recomputed_from": RECOMPUTED_FROM,
                "figures": {
                    key: {
                        "value": round(numer / enrol),
                        "numerator": round(numer),
                        **({"recomputed_value": round(_redo[field] / _redo["enrollment"])}
                           if _redo.get("enrollment") else {}),
                    }
                    for key, field, numer in (
                        ("total_per_student", "total", _tot),
                        ("local_per_student", "local", _loc),
                        ("state_per_student", "state", _st),
                        ("federal_per_student", "federal", _fed))
                },
            }
            for key, fig in _revenue["lineage"]["figures"].items():
                if "recomputed_value" not in fig:
                    unrecomputed.append(f"{num} {key}")
                    continue
                recomputed += 1
                if fig["recomputed_value"] != fig["value"]:
                    disagreements.append(
                        f"{num} {key}: built {fig['value']}, "
                        f"re-derived {fig['recomputed_value']}")
            # The three PERCENTAGES deliberately get no lineage entry. They are
            # not divisions: federal_pct is 100 minus the other two, so the bar's
            # labels add to 100 instead of to 99 or 101. Publishing a numerator
            # and denominator for it would describe a calculation that did not
            # happen, which is worse than publishing nothing.

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
            # WHO PAYS. TEA reports local M&O revenue net of recapture, so the
            # local share must be built from GROSS collections — otherwise a
            # property-wealthy district looks state-funded when in fact its
            # taxpayers paid and the state took a share away.
            "revenue": _revenue,
            "recapture": {"paid": round(recapture),
                          "per_student": round(recapture / row.fall_survey_enrollment),
                          "share_of_local_mo": round(recapture / gross_mo, 4) if gross_mo > 0 else 0.0},
        }
        # The spending card's evidence, on the same terms as revenue's. Only the
        # three REAL divisions get lineage: instruction, debt service and
        # operating each divide a published TEA column by enrollment. The card's
        # total is COMPOSED (rounded operating + rounded debt) and "everything
        # else" is a SUBTRACTION (operating minus instruction) — publishing a
        # numerator and denominator for either would describe a division that
        # never happened, the same rule that keeps federal_pct out of the
        # revenue lineage. The template notes say so where a reader will look.
        _sredo = redone_spend.get(num) or {}
        entry["allocation"]["lineage"] = {
            "denominator": round(enrol),
            "recomputed_from": SPEND_RECOMPUTED_FROM,
            "figures": {
                key: {
                    "value": val,
                    "numerator": round(float(row[col])),
                    **({"recomputed_value": round(_sredo[fld] / _sredo["enrollment"])}
                       if _sredo.get("enrollment") else {}),
                }
                for key, fld, col, val in (
                    ("spend_instruction_per_student", "instruction", INSTR, _instr),
                    ("spend_debt_per_student", "debt", DEBT, _debt),
                    ("spend_operating_per_student", "operating", TOTAL, _operating))
            },
        }
        for key, fig in entry["allocation"]["lineage"]["figures"].items():
            if "recomputed_value" not in fig:
                unrecomputed.append(f"{num} {key}")
                continue
            recomputed += 1
            if fig["recomputed_value"] != fig["value"]:
                disagreements.append(f"{num} {key}: built {fig['value']}, "
                                     f"re-derived {fig['recomputed_value']}")
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
            # What every district's revenue lineage means. Stored once, on
            # purpose: 1,202 copies of "the formula" is 1,202 chances for one of
            # them to say something different from the rest.
            #
            # `denominator_type` is not decoration. "Per student" is not a
            # definition — this site publishes per-student figures divided by
            # enrolment and others divided by different totals, and they
            # legitimately disagree. A figure that will not name its denominator
            # is refused by the publication gate rather than shown.
            "lineage_templates": {
                **{
                    key: {
                        "metric": f"revenue_{key}",
                        "formula": f"{label} / fall survey enrollment",
                        "denominator_type": "fall survey enrollment",
                        "unit": "USD per student",
                        "rounding": 0.5,
                        "fiscal_year": int(latest),
                        "source_id": "tea_peims",
                        "measure_id": "revenue_mix",
                        "source": "Texas Education Agency",
                        "source_note": ("local is GROSS property tax collections; "
                                        "TEA reports M&O revenue net of recapture, "
                                        "which understates property-funded "
                                        "districts"),
                        "artifact": "economics_data.json",
                    }
                    for key, label in (
                        ("total_per_student", "gross local + state + federal revenue"),
                        ("local_per_student",
                         "gross local M&O tax + I&S tax + other local revenue"),
                        ("state_per_student", "state revenue"),
                        ("federal_per_student", "federal revenue"),
                    )
                },
                # The spending card. Only its three real divisions appear here:
                # the card's TOTAL is composed from the rounded operating and
                # debt figures, and its "everything else" is operating minus
                # instruction — a template for either would describe a division
                # that never happened (the federal_pct rule, applied again).
                **{
                    key: {
                        "metric": key,
                        "formula": f"{label} / fall survey enrollment",
                        "denominator_type": "fall survey enrollment",
                        "unit": "USD per student",
                        "rounding": 0.5,
                        "fiscal_year": int(latest),
                        "source_id": "tea_peims",
                        "measure_id": measure,
                        "source": "Texas Education Agency",
                        "source_note": note,
                        "artifact": "economics_data.json",
                    }
                    for key, label, measure, note in (
                        ("spend_instruction_per_student",
                         "instruction spending (TEA functions 11-95)",
                         "instruction_share",
                         "instruction is TEA function codes 11-95, which include "
                         "classroom transfers"),
                        ("spend_debt_per_student",
                         "total debt service expenditure",
                         "debt_per_student",
                         "debt service sits OUTSIDE TEA's operating total; the "
                         "card's total is operating + debt, composed, never "
                         "subtracted"),
                        ("spend_operating_per_student",
                         "total operating expenditure by function",
                         "spend_per_student",
                         "excludes debt service and capital construction by "
                         "TEA's own definition of operating"),
                    )
                },
            },
            # The statewide headline's own evidence — the first number on the
            # site, so it must not be the last without any. Lives in meta, not
            # under any district, because it belongs to none of them.
            "lineage_statewide": statewide_lineage,
            # A check that ran and found nothing must not look like a check that
            # never ran. This is that distinction, recorded in the artefact.
            "lineage_recomputation": {
                "road": RECOMPUTED_FROM + "; " + SPEND_RECOMPUTED_FROM,
                "figures_checked": recomputed,
                "disagreements": len(disagreements),
                "not_recomputed": len(unrecomputed),
                "note": "Agreement means our two roads arrive at the same place. "
                        "It cannot make TEA's filing right — districts file PEIMS "
                        "and it is corrected for years afterwards.",
            },
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
            "revenue": statewide_revenue,
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
    # The artefact is written only if the two roads agree. A figure whose
    # independent re-derivation disagrees must not reach a reader while someone
    # decides what to do about it — that is the whole reason the second road
    # exists, and a warning nobody is watching is not a gate.
    if disagreements:
        print(f"REFUSING TO WRITE {args.out}: {len(disagreements)} figures "
              f"disagree with their re-derivation from TEA's own file.",
              file=sys.stderr)
        for line in disagreements[:20]:
            print(f"  {line}", file=sys.stderr)
        if len(disagreements) > 20:
            print(f"  ... and {len(disagreements) - 20} more", file=sys.stderr)
        print("  Fix the builder or scripts/recompute_revenue.py / "
              "recompute_spending.py — do not silence this.", file=sys.stderr)
        return 1

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

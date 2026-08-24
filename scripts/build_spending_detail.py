#!/usr/bin/env python3
"""Where the operating dollar actually goes — all sixteen PEIMS functions.

Every other layer here stops at three buckets: instruction, security, and
"operating". The other fourteen function codes have been in the warehouse since
day one — `to_sql` puts all 140 CSV columns in `texas_school_finance` — and
were exposed by nothing. Not `v_finance_summary`, not the API, not the
artefacts, not the agent. A coverage simulation on 2026-08-23 put that single
gap at 8.9% of all realistic inquiries and +7.65 points of answerability, the
largest item on the board and the only one needing no new source.

The OBJECT and PROGRAM cuts were in better shape and the first draft of that
finding overstated it: `sql/create_detail_view.sql` has published them through
`/district/{n}/spending-detail` all along. But that route needs a live
database, is absent from the artefact set, and `nlp_reader` cannot read the
view — so the agent could not reach them either. They are folded in here so
all three cuts are DB-free and answerable the same way.

So this publishes them: buses, meals, athletics, counsellors, health, campus
and central administration, plant, data processing, community services — per
district, against the state, with a percentile.

Three rules the figures obey:

**Share is of OPERATING, never of total.** The sixteen functions sum to
`all_funds_total_operating_expenditures_by_obj` (0.9996-1.0000 every year, which
`build_trend_data.py` re-checks on every build). Total disbursements also carry
bond-funded construction and debt service, so a share taken against it would
make a district mid-build look like it spends less on children — the same trap
`v_finance_summary`'s own comment warns about.

**A percentile is over districts that REPORTED, never over all 1,202.** A
district reporting no food service is usually one that runs none, and counting
it as a zero would drag every other district's rank up.

**Real dollars use the site's existing CPI-U factors**, taken from the
economics artefact, so a figure here is on the same price base as one anywhere
else on the site.

Usage:
    python scripts/build_spending_detail.py
    python scripts/build_spending_detail.py --finance data/texas_finance_clean.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# The sixteen PEIMS function codes, in the order a reader should meet them:
# what happens in front of children first, the building next, the office last.
FUNCTIONS = [
    ("instruction", "all_funds_instruction_transfer_expend_fct11_95",
     "Instruction", "11,95", "Teachers and everything that happens in a classroom."),
    ("resources", "all_funds_instruc_resource_media_service_exp_fct12",
     "Libraries and media", "12", "Library books, media services, instructional resources."),
    ("curriculum", "all_funds_curriculum_staff_development_exp_fct13",
     "Curriculum and teacher training", "13", "Writing curriculum and training the staff who teach it."),
    ("instr_leadership", "all_funds_instruc_leadership_expend_fct21",
     "Instructional leadership", "21", "District staff who direct and supervise teaching."),
    ("campus_admin", "all_funds_campus_administration_expend_fct23",
     "Principals' offices", "23", "Principals, assistant principals and campus office staff."),
    ("counseling", "all_funds_guidance_counseling_services_exp_fct31",
     "Counsellors", "31", "Guidance, counselling and evaluation services."),
    ("social_work", "all_funds_social_work_services_exp_fct32",
     "Social work", "32", "Attendance and social work services."),
    ("health", "all_funds_health_services_exp_fct33",
     "Health services", "33", "School nurses and health services."),
    ("transportation", "all_funds_transportation_expenditures_fct34",
     "Buses", "34", "Getting students to school and home again."),
    ("food", "all_funds_food_service_expenditures_fct35",
     "School meals", "35", "Breakfast, lunch and the staff who serve them."),
    ("extracurricular", "all_funds_extracurricular_expenditures_fct36",
     "Sport, band and clubs", "36", "Athletics, band, UIL and other activities outside class."),
    ("general_admin", "all_funds_general_administrat_expend_fct41_92",
     "Central administration", "41,92", "The superintendent's office, business office, board."),
    ("plant", "all_funds_plant_maintenance_opera_expend_fct51",
     "Keeping buildings open", "51", "Utilities, custodians, maintenance, groundskeeping."),
    ("security", "all_funds_security_monitoring_service_expend_fct52",
     "Security", "52", "Officers, monitoring, and school safety."),
    ("data_processing", "all_funds_data_processing_services_expend_fct53",
     "Technology services", "53", "Data processing and district technology operations."),
    ("community", "all_funds_community_services_fct61",
     "Community services", "61", "Services to the community beyond enrolled students."),
]

# WHO the money served — PEIMS program-intent codes. These were already in a
# view (v_spending_detail, DB-backed and not reachable by the agent); publishing
# them here puts special education, bilingual and athletics on the same DB-free
# footing as everything else on the site.
#
# Programs do NOT sum to operating: `undistributed` (99) carries what is not
# assigned to a program, and the total below is TEA's own program total, not
# our addition. Never present a program share as a share of operating spend.
PROGRAMS = [
    ("regular", "all_funds_regular_program_expend_11", "Regular programme", "11",
     "The mainstream classroom."),
    ("gifted", "all_funds_gifted_talented_program_expend_21", "Gifted and talented", "21",
     "Programmes for identified gifted students."),
    ("career_tech", "all_funds_career_technology_pgm_expend_22", "Career and technical", "22",
     "Vocational and technical education."),
    ("special_ed", "all_funds_students_with_disabilities_pgm_expend_23",
     "Special education", "23", "Services for students with disabilities."),
    ("compensatory", "all_funds_state_compensatory_ed_expend_24_26_28_29_30_34",
     "State compensatory education", "24,26,28-30,34",
     "Extra support for students at risk of dropping out."),
    ("bilingual", "all_funds_bilingual_program_exp_25_35", "Bilingual and ESL", "25,35",
     "Instruction for emergent bilingual students."),
    ("athletics", "all_funds_athletics_program_expend_91", "Athletics", "91",
     "The athletics programme specifically, as TEA codes it."),
    ("undistributed", "all_funds_undistributed_program_exp_99", "Not assigned to a programme",
     "99", "Spending TEA's file does not attribute to any programme."),
]
PROGRAM_TOTAL = "all_funds_total_program_operating_expenditures"

# What the money was bought AS, rather than what it was bought FOR.
OBJECTS = [
    ("payroll", "all_funds_total_payroll_expenditures", "People",
     "Salaries and benefits for everyone the district employs."),
    ("contracted", "all_funds_total_professional_contracted_services_expenditure",
     "Contracted services", "Outside professionals and contracted services."),
    ("supplies", "all_funds_total_supplies_materials_expenditures", "Supplies and materials",
     "Everything consumed: books, paper, fuel, food stock."),
    ("other", "all_funds_total_other_operating_expenditures", "Other operating",
     "Travel, insurance, utilities billed as other operating costs."),
]

OPERATING = "all_funds_total_operating_expenditures_by_obj"
ENROLL = "fall_survey_enrollment"

# Below this a per-student figure is noise, not a finding: a 40-student district
# buying one bus reads as an extraordinary transport budget.
MIN_STUDENTS = 100


def deflator(econ: dict) -> dict[int, float]:
    """CPI-U factors to constant 2024 dollars, from the layer that publishes
    both nominal and real per-student spending. Reusing it keeps every figure
    on this site on one price base."""
    return {int(r["year"]): r["spend_per_student_real"] / r["spend_per_student_nominal"]
            for r in econ["macro"]["spending"] if r.get("spend_per_student_nominal")}


def load(csv: Path) -> pd.DataFrame:
    cols = ["district_number", "district_name", "year", ENROLL, OPERATING]
    cols += [c for _, c, *_ in FUNCTIONS] + [c for _, c, *_ in OBJECTS]
    cols += [c for _, c, *_ in PROGRAMS] + [PROGRAM_TOTAL]
    d = pd.read_csv(csv, dtype={"district_number": str}, low_memory=False,
                    usecols=lambda c: c in set(cols))
    for c in cols:
        if c not in ("district_number", "district_name"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def percentiles(series: pd.Series) -> dict[str, int]:
    """Rank among districts that REPORTED this function, not among all of them.

    A district with no food service line usually runs no food service. Treating
    that as a zero would push every other district's percentile up and invent a
    finding out of an absence."""
    s = series.dropna()
    s = s[s > 0]
    if s.empty:
        return {}
    ranks = s.rank(pct=True) * 100
    return {k: int(np.floor(v)) for k, v in ranks.items()}


def build(d: pd.DataFrame, defl: dict[int, float]) -> dict:
    year = int(d.year.max())
    cur = d[d.year == year].copy()
    first_year = int(d.year.min())
    first = d[d.year == first_year].copy()

    cur = cur[cur[ENROLL].fillna(0) > 0]
    cur = cur.set_index("district_number")
    first = first[first[ENROLL].fillna(0) > 0].set_index("district_number")

    op = cur[OPERATING]
    enr = cur[ENROLL]

    # Per-student tables, one column per function, used for both the district
    # payload and the statewide leaderboards.
    ps = pd.DataFrame(index=cur.index)
    share = pd.DataFrame(index=cur.index)
    for key, col, *_ in FUNCTIONS:
        ps[key] = cur[col] / enr
        share[key] = cur[col] / op * 100

    first_share = pd.DataFrame(index=first.index)
    for key, col, *_ in FUNCTIONS:
        first_share[key] = first[col] / first[OPERATING] * 100

    # Percentiles and medians only over districts big enough to be meaningful.
    big = enr >= MIN_STUDENTS
    pct = {key: percentiles(ps.loc[big, key]) for key, *_ in FUNCTIONS}
    med = {key: (float(ps.loc[big, key].dropna()[ps.loc[big, key].dropna() > 0].median())
                 if not ps.loc[big, key].dropna().empty else None)
           for key, *_ in FUNCTIONS}

    obj_ps = pd.DataFrame(index=cur.index)
    for key, col, *_ in OBJECTS:
        obj_ps[key] = cur[col] / enr
    obj_total = sum(cur[col].fillna(0) for _, col, *_ in OBJECTS)

    districts: dict[str, dict] = {}
    for dn in cur.index:
        students = float(enr.loc[dn])
        operating = float(op.loc[dn]) if pd.notna(op.loc[dn]) else None
        if not operating or operating <= 0:
            continue
        funcs = {}
        for key, col, *_ in FUNCTIONS:
            amount = cur.at[dn, col]
            if pd.isna(amount) or amount == 0:
                continue           # absent, and an absence is not a zero
            rec = {
                "amount": int(round(float(amount))),
                "per_student": round(float(amount) / students, 2),
                "share_of_operating": round(float(amount) / operating * 100, 2),
            }
            if dn in pct[key]:
                rec["percentile"] = pct[key][dn]
            if dn in first_share.index and pd.notna(first_share.at[dn, key]):
                rec["share_first_year"] = round(float(first_share.at[dn, key]), 2)
            funcs[key] = rec

        objs = {}
        ot = float(obj_total.loc[dn])
        for key, col, *_ in OBJECTS:
            amount = cur.at[dn, col]
            if pd.isna(amount) or amount == 0:
                continue
            objs[key] = {
                "amount": int(round(float(amount))),
                "per_student": round(float(amount) / students, 2),
                "share": round(float(amount) / ot * 100, 2) if ot else None,
            }

        progs = {}
        ptot = cur.at[dn, PROGRAM_TOTAL]
        ptot = float(ptot) if pd.notna(ptot) and float(ptot) > 0 else None
        for key, col, *_ in PROGRAMS:
            amount = cur.at[dn, col]
            if pd.isna(amount) or amount == 0:
                continue
            progs[key] = {
                "amount": int(round(float(amount))),
                "per_student": round(float(amount) / students, 2),
                # Share of TEA's own PROGRAM total, never of operating: the
                # programme codes do not tile operating spend.
                "share_of_program_total": (round(float(amount) / ptot * 100, 2)
                                           if ptot else None),
            }

        # Does the sixteen add back up? Published per district so a reader can
        # check rather than trust — and so a future TEA restatement is visible.
        covered = sum(float(cur.at[dn, col]) for _, col, *_ in FUNCTIONS
                      if pd.notna(cur.at[dn, col]))
        districts[dn] = {
            "district_name": str(cur.at[dn, "district_name"]),
            "year": year,
            "students": int(round(students)),
            "operating_total": int(round(operating)),
            "operating_per_student": round(operating / students, 2),
            "functions": funcs,
            "objects": objs,
            "programs": progs,
            "reconciles": round(covered / operating, 4),
            "small_district": bool(students < MIN_STUDENTS),
        }

    # Statewide: medians, the state's own split, and a leaderboard per function.
    state_op = float(op.sum())
    state_enr = float(enr.sum())
    state_funcs = {}
    for key, col, label, code, blurb in FUNCTIONS:
        total = float(cur[col].sum())
        reporting = int((cur[col].fillna(0) > 0).sum())
        state_funcs[key] = {
            "label": label, "function_code": code, "what_it_is": blurb,
            "total": int(round(total)),
            "per_student": round(total / state_enr, 2),
            "share_of_operating": round(total / state_op * 100, 2),
            "median_per_student": round(med[key], 2) if med[key] else None,
            "districts_reporting": reporting,
        }

    leaders = {}
    for key, *_ in FUNCTIONS:
        col = ps.loc[big, key].dropna()
        col = col[col > 0].sort_values(ascending=False)
        leaders[key] = [
            {"district_number": dn, "district_name": str(cur.at[dn, "district_name"]),
             "per_student": round(float(v), 2),
             "share_of_operating": round(float(share.at[dn, key]), 2),
             "students": int(round(float(enr.loc[dn])))}
            for dn, v in col.head(15).items()
        ]

    state_progs = {}
    state_ptot = float(cur[PROGRAM_TOTAL].sum())
    for key, col, label, code, blurb in PROGRAMS:
        total = float(cur[col].sum())
        state_progs[key] = {
            "label": label, "program_code": code, "what_it_is": blurb,
            "total": int(round(total)),
            "per_student": round(total / state_enr, 2),
            "share_of_program_total": round(total / state_ptot * 100, 2),
            "districts_reporting": int((cur[col].fillna(0) > 0).sum()),
        }

    state_objs = {}
    ot = float(sum(cur[col].sum() for _, col, *_ in OBJECTS))
    for key, col, label, blurb in OBJECTS:
        total = float(cur[col].sum())
        state_objs[key] = {
            "label": label, "what_it_is": blurb,
            "total": int(round(total)),
            "per_student": round(total / state_enr, 2),
            "share": round(total / ot * 100, 2),
        }

    recon = pd.Series({dn: r["reconciles"] for dn, r in districts.items()})
    return {
        "meta": {
            "year": year,
            "first_year": first_year,
            "source": "TEA Summarized PEIMS Actual Financial Data",
            "publisher": "Texas Education Agency",
            "built_from": "data/texas_finance_clean.csv",
            "districts": len(districts),
            "functions": len(FUNCTIONS),
            "programs": len(PROGRAMS),
            "objects": len(OBJECTS),
            "min_students_for_percentile": MIN_STUDENTS,
            "denominator": (
                "Every share is of ALL-FUNDS OPERATING expenditure "
                f"({OPERATING}), never of total disbursements. Total "
                "disbursements also carry bond-funded construction and debt "
                "service, so a share taken against it would make a district "
                "mid-build look like it spends less on children."),
            "reconciliation": {
                "median": round(float(recon.median()), 4),
                "min": round(float(recon.min()), 4),
                "max": round(float(recon.max()), 4),
                "reading": ("The sixteen functions should sum to the operating "
                            "total. Published per district so a reader can check "
                            "rather than trust."),
            },
            "limits": [
                "These are ACTUAL expenditures for the fiscal year shown, not a "
                "budget and not the current year.",
                "A function absent for a district is left out, never written as "
                "zero: a district with no food service line usually runs none, "
                "and a zero would rank every other district up.",
                f"Percentiles and medians are over districts with at least "
                f"{MIN_STUDENTS} students that reported the function. Below that "
                f"one bus is an outlier.",
                "Function codes describe what money was spent ON; PROGRAM codes "
                "describe who it served. They are two different cuts of the same "
                "operating dollar and must never be added together.",
                "Programme codes do NOT tile operating spend — code 99 carries "
                "what TEA does not attribute to a programme — so a programme "
                "share is taken against TEA's own programme total, never against "
                "operating.",
                "Central administration (41,92) is not 'overhead' and campus "
                "administration (23) is principals, not bureaucrats. Comparing "
                "either across districts of very different size mostly measures "
                "size.",
            ],
        },
        "texas": {
            "year": year,
            "students": int(round(state_enr)),
            "operating_total": int(round(state_op)),
            "operating_per_student": round(state_op / state_enr, 2),
            "functions": state_funcs,
            "objects": state_objs,
            "programs": state_progs,
        },
        "leaderboards": leaders,
        "districts": districts,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finance", default="data/texas_finance_clean.csv")
    ap.add_argument("--economics", default="static/economics_data.json")
    ap.add_argument("--out", default="static/spending_detail.json")
    args = ap.parse_args()

    csv = ROOT / args.finance
    if not csv.exists():
        print(f"{args.finance} is absent. Rebuild it with "
              f"scripts/prepare_data.py from TEA's workbook.", file=__import__("sys").stderr)
        return 1

    d = load(csv)
    econ = json.loads((ROOT / args.economics).read_text())
    payload = build(d, deflator(econ))

    out = ROOT / args.out
    out.write_text(json.dumps(payload, separators=(",", ":")))
    m = payload["meta"]
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  {m['districts']:,} districts · fiscal {m['year']} · "
          f"{m['functions']} function codes")
    print(f"  reconciliation median {m['reconciliation']['median']:.4f} "
          f"(min {m['reconciliation']['min']:.4f}, max {m['reconciliation']['max']:.4f})")
    tx = payload["texas"]["functions"]
    for k in ("instruction", "general_admin", "transportation", "food",
              "extracurricular", "counseling"):
        f = tx[k]
        print(f"  {f['label']:<28} ${f['per_student']:>9,.0f}/student  "
              f"{f['share_of_operating']:>5.2f}% of operating")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

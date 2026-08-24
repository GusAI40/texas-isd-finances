#!/usr/bin/env python3
"""Monte Carlo data-coverage and answerability test.

The question this answers is NOT "can the model produce a plausible reply".
It is:

    Of the questions real people are likely to ask this portal over 90 days,
    what share can be answered accurately and completely from the data the
    application ACTUALLY holds?

So nothing here asks a language model anything. Every inquiry is resolved by
probing the real artefacts, the real database views, and a registry of
capabilities whose availability was verified by inspection — never by reading
a claim in a doc or a route in the code. A question counts as answerable only
when the fields its answer needs resolve to real values for the district that
was actually sampled.

Two rules keep the score honest:

**The question bank is written from user needs, not from the schema.** If the
bank were derived from the fields we hold, coverage would be 100% by
construction and would measure nothing. Roughly a third of the templates below
are things we cannot answer at all — they are in here precisely because people
ask them.

**An honest refusal is not always an answer.** `src/absences.py` separates
three kinds of nothing. NOT_APPLICABLE ("a charter levies no property tax")
and DID_NOT_HAPPEN ("no bond election was ever held here") ARE complete
answers to the question asked, and score as such. NOT_MEASURED ("we do not
have this") is graded as partial: saying so is the right behaviour, but the
reader still leaves without the fact.

Usage:
    python scripts/coverage_simulation.py                 # 5 seeds, ~12k each
    python scripts/coverage_simulation.py --seeds 1 --inquiries 2000
    python scripts/coverage_simulation.py --json out.json --markdown out.md
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

# --------------------------------------------------------------------------
# 1. THE DATA CAPABILITY MAP — what the system actually knows.
# --------------------------------------------------------------------------

ARTIFACTS = {
    "eco": "economics_data.json",
    "out": "outcomes_data.json",
    "forensic": "forensic_data.json",
    "trend": "trend_data.json",
    "bond": "bond_data.json",
    "debt": "debt_data.json",
    "campus": "campus_data.json",
    "equity": "equity_data.json",
    "erate": "erate_data.json",
    "national": "national_data.json",
    "geo": "district_geo.json",
    "spend": "spending_detail.json",
    "tax": "tax_history.json",
    "perf": "campus_performance.json",
}

# Which absence sentence covers a missing district record, and what kind of
# nothing it is. NOT_APPLICABLE / DID_NOT_HAPPEN answer the question;
# NOT_MEASURED does not. Verified against src/absences.py, not assumed.
ABSENCE_KIND = {
    "bond": ("did_not_happen", "not_applicable"),      # (non-charter, charter)
    "debt": ("did_not_happen", "did_not_happen"),
    "erate": ("did_not_happen", "did_not_happen"),
    "national": ("not_measured", "not_applicable"),
    "campus": ("not_measured", "not_measured"),
    "equity": ("not_measured", "not_measured"),
    "trend": ("not_measured", "not_measured"),
    "out": ("not_measured", "not_measured"),
    "eco": ("not_measured", "not_measured"),
    "forensic": ("not_measured", "not_measured"),
    "geo": ("not_applicable", "not_applicable"),       # charters have no boundary
    "spend": ("not_measured", "not_measured"),
    "tax": ("not_measured", "not_applicable"),   # a charter levies no tax
    "perf": ("not_measured", "not_measured"),
}

# Capabilities that are not a per-district field lookup. `state` is one of
# PRESENT / ABSENT / UNUSABLE. UNUSABLE means the data demonstrably exists but
# cannot be reached by any published surface — that is a different problem with
# a different fix, so it gets its own grade (D) rather than being lumped in
# with "we never collected it".
CAPABILITIES: dict[str, dict[str, Any]] = {
    "peer_compare": {
        "state": "PRESENT",
        "evidence": "economics_data.json districts[*].who_does_better (matched peers); "
                    "outcomes_data.json spend_peer_median",
    },
    "statewide_leaderboard": {
        "state": "PRESENT",
        "evidence": "forensic_data.json leaderboards{debt_per_student, recapture_per_student, "
                    "approved_per_student, beats_prediction}",
    },
    "time_series_17y": {
        "state": "PRESENT",
        "evidence": "trend_data.json districts[*].series — 17 points, fiscal 2009-2025",
    },
    "cross_state": {
        "state": "PRESENT",
        "evidence": "national_data.json states.rows — 51 jurisdictions, Census F-33 FY2024",
    },
    "campus_ratings": {
        "state": "PRESENT",
        "evidence": "campus_data.json districts[*].campuses — 9,084 campuses with rating+score",
    },
    "raw_download": {
        "state": "PRESENT",
        "evidence": "docs/RAW_DATA_ARCHIVE.md manifest + /feed.xml + committed static/*.json",
    },
    "api_access": {
        "state": "PRESENT",
        "evidence": "/docs OpenAPI; POST /mcp serves 11 read-only tools",
    },
    "lineage": {
        "state": "PRESENT",
        "evidence": "/district/{n}/lineage/{metric} — 8,416 figures gated at build",
    },
    "nl_query": {
        "state": "PRESENT",
        "evidence": "POST /query — LangChain agent over v_finance_summary + v_anomaly_flags",
    },

    # --- Closed 2026-08-24: was held in the warehouse, exposed by nothing ---
    "function_level_spend": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24. All 16 function codes now publish per district in "
                    "spending_detail.json (/district/{n}/spending, /spending/texas) and "
                    "v_finance_summary was widened from 12 to 30 columns so the agent can "
                    "reach them too. Re-derived from TEA's own file by "
                    "tests/test_provenance_layers.py with the csv module, no builder "
                    "imported. Was UNUSABLE: held in the 140-column table, exposed by "
                    "nothing.",
        "fix": "Done.",
    },
    "object_level_spend": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24. payroll / contracted services / supplies now "
                    "publish per district in spending_detail.json objects{} and in the "
                    "widened v_finance_summary.",
        "fix": "Done.",
    },
    "fund_balance": {
        "state": "ABSENT",
        "evidence": "No fund-balance / reserve column appears in any artefact, in "
                    "v_finance_summary, or in the columns any builder reads. TEA publishes "
                    "it in a different product (AFR) that this project has never ingested.",
        "fix": "Ingest TEA's Actual Financial Report fund-balance file.",
    },

    # --- Never collected ---------------------------------------------------
    "campus_finance": {
        "state": "ABSENT",
        "evidence": "campus_data.json carries rating, score, students, pct_poor — no dollars. "
                    "Every financial figure in this repo stops at the district.",
        "fix": "TAPR campus files (already the named next fountain in CLAUDE.md).",
    },
    "campus_staff": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24 via TAPR. Per-campus teacher FTE, average experience, tenure in district, "
                    "beginning-teacher share, degree mix and average salary for 8,204 campuses. Campus-level TURNOVER "
                    "is still not published by TAPR.",
        "fix": "TAPR campus files.",
    },
    "campus_turnover": {
        "state": "ABSENT",
        "evidence": "TAPR's staff dataset publishes campus teacher FTE, experience, "
                    "tenure, beginning-teacher share and degree mix — but not turnover. "
                    "Turnover exists at DISTRICT grain only (STURN).",
        "fix": "No campus-grain turnover is published by TEA in this product.",
    },
    "teacher_certification": {
        "state": "ABSENT",
        "evidence": "No certification field in any artefact.",
        "fix": "TAPR.",
    },
    "staar_by_grade": {
        "state": "ABSENT",
        "evidence": "equity_data.json holds district totals by subject "
                    "(reading/math) only — no grade level.",
        "fix": "TEA STAAR district file at grade grain (currently login-gated).",
    },
    "staar_by_race": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24 via TAPR. District results for 15 student groups including African American, "
                    "Hispanic, White, Asian, American Indian, Pacific Islander and Two or More Races.",
        "fix": "Same STAAR ingest, more subgroups.",
    },
    "campus_staar": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24 via TAPR. campus_performance.json publishes STAAR "
                    "by subject for 8,264 campuses; "
                    "the TEA SAS broker download that CLAUDE.md recorded as needing a human is mapped in "
                    "scripts/ingest_tapr.py.",
        "fix": "TEA campus STAAR file.",
    },
    "salaries_named": {
        "state": "ABSENT",
        "evidence": "No individual-salary or superintendent-pay field anywhere.",
        "fix": "TEA superintendent salary file / district AFRs.",
    },
    "vendor_contracts": {
        "state": "ABSENT",
        "evidence": "No payables, vendor, or contract data ingested.",
        "fix": "Per-district check registers — no statewide publisher exists.",
    },
    "bond_projects": {
        "state": "ABSENT",
        "evidence": "bond elections carry date/amount/purpose CATEGORY/vote counts — no "
                    "project list, no spend-against-bond.",
        "fix": "District bond project pages; no statewide source.",
    },
    "budget_forward": {
        "state": "ABSENT",
        "evidence": "Every finance figure is ACTUAL (PEIMS actuals, fiscal 2009-2025). No "
                    "adopted budget, no current-year figure.",
        "fix": "Ingest adopted budgets, or state clearly that the site is historical.",
    },
    "enrollment_forecast": {
        "state": "ABSENT",
        "evidence": "No projection model. trend series ends at the last actual year.",
        "fix": "A demographic model — and an error bar, or it should not ship.",
    },
    "state_aid_formula": {
        "state": "ABSENT",
        "evidence": "Revenue is split local/state/federal only. No FSP allotment detail, no "
                    "basic allotment, no tier composition.",
        "fix": "TEA Summary of Finance (SOF) reports.",
    },
    "tax_rate_history": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24 from data already in the repo's own ingest. "
                    "tax_history.json publishes mo/is/total rate and the taxable value "
                    "roll per district 2009-2024 (1,015 districts), plus the rate-vs-value "
                    "decomposition. The rates were always in data/tea_property.csv; only "
                    "the latest row had ever been read.",
        "fix": "Done.",
    },
    "parcel_tax": {
        "state": "ABSENT",
        "evidence": "Tax bill is modelled on a fixed $300,000 home, stated as such. No "
                    "appraisal roll, no individual property.",
        "fix": "Out of scope — county appraisal districts, 254 of them.",
    },
    "attendance_zones": {
        "state": "ABSENT",
        "evidence": "district_geo.json holds DISTRICT boundaries only (1,016). No campus "
                    "attendance zones.",
        "fix": "No statewide publisher; 1,200 district GIS sources.",
    },
    "conservatorship": {
        "state": "ABSENT",
        "evidence": "Only Houston's 2023 takeover is modelled (takeover_data.json), as a "
                    "one-district study. No statewide intervention register.",
        "fix": "TEA intervention list.",
    },
    "discipline_data": {
        "state": "ABSENT",
        "evidence": "No discipline, safety-incident, or PEIMS 425 data.",
        "fix": "TEA discipline data.",
    },
    "special_ed_spend": {
        "state": "PRESENT",
        "evidence": "CLOSED 2026-08-24, and the first reading of this gap was WRONG. It "
                    "said special-education spending was 'a different PEIMS product'. It "
                    "is not: all_funds_students_with_disabilities_pgm_expend_23 is in the "
                    "same CSV, and sql/create_detail_view.sql had already exposed it "
                    "through a DB-backed route. Now published DB-free per district in "
                    "spending_detail.json programs{} — statewide $1,820/student, 14.1% of "
                    "the programme total.",
        "fix": "Done.",
    },
    "charter_comparison": {
        "state": "PARTIAL",
        "evidence": "Charters carry finance + campus ratings but have NO bond, NO debt, NO "
                    "boundary and NO Census F-33 row (282 in national.absent). Comparisons "
                    "spanning those layers cannot be made whole.",
        "fix": "Structural — a charter is not a taxing government.",
    },
    "current_year": {
        "state": "ABSENT",
        "evidence": "Latest finance year is 2025, outcomes 2024, national FY2024. A question "
                    "about this month cannot be answered by any of them.",
        "fix": "Structural — TEA publishes with a lag.",
    },
}

# Absences that apply to a SECTION rather than a whole district record. A
# charter's missing tax figure is not a gap — a charter levies no property tax,
# and src/absences.py:no_tax_figure says so. An empty flags list is likewise the
# answer ("nothing crossed a published threshold"), not a blank.
PATH_ABSENCE = {
    ("eco", "tax"): ("not_measured", "not_applicable"),           # no_tax_figure
    ("eco", "who_does_better"): ("did_not_happen", "did_not_happen"),  # no_better_peer
    ("forensic", "flags"): ("did_not_happen", "did_not_happen"),
    ("out", "expectation"): ("not_measured", "not_measured"),     # no_where_it_landed
    ("forensic", "where_it_landed"): ("not_measured", "not_measured"),
}

PARTIAL_STATES = {"PARTIAL"}

# Capabilities temporarily treated as available, for what-if re-simulation.
# Empty during the baseline run — the score never sees it.
GRANTED: set[str] = set()


class Capability:
    """The verified index. Every lookup hits real loaded data."""

    def __init__(self) -> None:
        self.art: dict[str, dict] = {}
        for key, fname in ARTIFACTS.items():
            blob = json.loads((STATIC / fname).read_text())
            self.art[key] = blob.get("districts") or blob.get("d") or {}
        self.meta = {
            k: json.loads((STATIC / v).read_text()).get("meta", {})
            for k, v in ARTIFACTS.items()
        }
        self.charter: dict[str, bool] = {}
        self.name: dict[str, str] = {}
        with (ROOT / "data/district_crosswalk.csv").open() as fh:
            for row in csv.DictReader(fh):
                self.charter[row["district_number"]] = row["is_charter"] == "True"
                self.name[row["district_number"]] = row["district_name"]
        eco = self.art["eco"]
        self.enrollment = {
            d: (rec.get("students") or 0) for d, rec in eco.items()
        }
        self.districts = sorted(eco)

    def probe(self, district: str, spec: str) -> tuple[str, str]:
        """Resolve one requirement. Returns (state, why).

        state is PRESENT / ABSENT / UNUSABLE / EXPLAINED / UNMEASURED.
        EXPLAINED   — record missing, but an absence sentence answers the
                      question outright (not applicable / did not happen).
        UNMEASURED  — record missing and the honest answer is "we do not know".
        """
        if spec.startswith("cap:"):
            name = spec[4:]
            if name in GRANTED:           # what-if: pretend this gap were closed
                return "PRESENT", f"cap:{name} (granted in what-if)"
            entry = CAPABILITIES[name]
            state = entry["state"]
            if state in PARTIAL_STATES:
                return "UNMEASURED", entry["evidence"]
            return state, entry["evidence"]

        art_key, _, path = spec.partition(":")
        table = self.art[art_key]
        rec = table.get(district)
        if rec is None:
            non_charter, charter = ABSENCE_KIND[art_key]
            kind = charter if self.charter.get(district) else non_charter
            if kind in ("not_applicable", "did_not_happen"):
                return "EXPLAINED", f"{art_key}: absence is the answer ({kind})"
            return "UNMEASURED", f"{art_key}: no record, absence kind={kind}"

        node: Any = rec
        if not path:                      # "geo:" — the record's existence IS the answer
            return "PRESENT", f"{art_key}: record present"

        def section_absence() -> tuple[str, str]:
            key = (art_key, path.split(".")[0])
            if key not in PATH_ABSENCE:
                return "UNMEASURED", f"{art_key}: {path} not held for this district"
            non_charter, charter = PATH_ABSENCE[key]
            kind = charter if self.charter.get(district) else non_charter
            if kind in ("not_applicable", "did_not_happen"):
                return "EXPLAINED", f"{art_key}:{path} absence is the answer ({kind})"
            return "UNMEASURED", f"{art_key}:{path} absent, kind={kind}"

        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return section_absence()
            node = node[part]
        if node is None or (isinstance(node, (list, dict)) and len(node) == 0):
            return section_absence()
        return "PRESENT", f"{art_key}:{path}"


# --------------------------------------------------------------------------
# 2. PERSONAS — who actually shows up.
# --------------------------------------------------------------------------
# Shares are a judgement about a public transparency portal, and they are an
# ASSUMPTION, recorded here so the reader can disagree with it. Sensitivity to
# this mix is reported in the output.
PERSONAS = {
    "parent_resident": 0.42,
    "taxpayer_voter": 0.16,
    "journalist": 0.09,
    "district_leader": 0.11,
    "board_trustee": 0.06,
    "policy_researcher": 0.08,
    "realtor_relocating": 0.05,
    "vendor_prospect": 0.03,
}

# Questions per user over 90 days, by persona. A parent checks once and leaves;
# a journalist and an analyst come back.
DEPTH = {
    "parent_resident": (1, 4),
    "taxpayer_voter": (1, 3),
    "journalist": (4, 25),
    "district_leader": (3, 14),
    "board_trustee": (2, 9),
    "policy_researcher": (5, 30),
    "realtor_relocating": (2, 8),
    "vendor_prospect": (1, 4),
}

CRITICAL, HIGH, NORMAL = 5, 3, 1


def Q(qid, text, cat, importance, personas, requires, partial_ok=False, note=""):
    return {
        "id": qid, "text": text, "cat": cat, "importance": importance,
        "personas": personas, "requires": requires, "partial_ok": partial_ok,
        "note": note,
    }


P_ALL = tuple(PERSONAS)
P_PUBLIC = ("parent_resident", "taxpayer_voter", "realtor_relocating")
P_PRO = ("journalist", "policy_researcher", "district_leader", "board_trustee")

# --------------------------------------------------------------------------
# 3. THE QUESTION BANK — written from what people ask, not from what we hold.
# --------------------------------------------------------------------------
QUESTIONS = [
    # ---- money, current status -------------------------------------------
    Q("spend_ps", "How much does {d} spend per student?", "current_status", CRITICAL,
      P_ALL, ["eco:allocation.total_per_student"]),
    Q("operating_ps", "How much of that actually runs the schools?", "current_status", HIGH,
      P_ALL, ["eco:allocation.operating_per_student"]),
    Q("instruction_ps", "How much reaches the classroom in {d}?", "current_status", CRITICAL,
      P_ALL, ["eco:allocation.instruction_per_student"]),
    Q("payroll", "What share of {d}'s budget is payroll?", "financial", NORMAL,
      P_PRO, ["eco:allocation.payroll_per_student", "eco:allocation.operating_per_student"]),
    Q("enrollment", "How many students does {d} have?", "current_status", HIGH,
      P_ALL, ["eco:students"]),
    Q("revenue_mix", "Where does {d}'s money come from?", "financial", HIGH,
      P_ALL, ["eco:revenue.local_pct", "eco:revenue.state_pct", "eco:revenue.federal_pct"]),
    Q("federal_money", "How much federal money does {d} get?", "financial", NORMAL,
      P_ALL, ["eco:revenue.federal_per_student"]),
    Q("erate", "How much E-Rate funding has {d} drawn?", "financial", NORMAL,
      P_PRO, ["erate:committed", "erate:disbursed"]),

    # ---- what people ask about their own tax bill -------------------------
    Q("tax_bill", "What do I pay to {d} on a $300,000 home?", "financial", CRITICAL,
      P_PUBLIC + ("board_trustee",), ["eco:tax.bill_on_home", "eco:tax.total_rate"]),
    Q("tax_rate", "What is {d}'s tax rate?", "financial", HIGH, P_ALL, ["eco:tax.total_rate"]),
    Q("recapture", "How much of {d}'s money leaves under recapture?", "financial", HIGH,
      P_ALL, ["eco:recapture.per_student", "eco:tax.leaves_district"]),
    Q("tax_why_up", "Why did my school tax bill go up this year?", "root_cause", CRITICAL,
      P_PUBLIC, ["tax:change.rate_change_pct", "tax:change.taxable_value_change_pct",
                 "tax:change.reading"],
      note="Answered as a decomposition — what the RATE did against what VALUES "
           "did. A parcel-level answer would still need an appraisal roll."),
    Q("tax_my_house", "What will I pay on MY house in {d}?", "financial", HIGH,
      P_PUBLIC, ["cap:parcel_tax"]),
    Q("tax_rate_trend", "Has {d}'s tax rate gone up over the last ten years?", "trend", HIGH,
      P_ALL, ["tax:series.total_rate", "tax:change.rate_change_pct"]),

    # ---- comparison -------------------------------------------------------
    Q("vs_peers", "Is {d} spending more than similar districts?", "comparison", CRITICAL,
      P_ALL, ["out:spend_per_student", "out:spend_peer_median", "cap:peer_compare"]),
    Q("vs_state", "How does {d} compare to the state?", "comparison", HIGH,
      P_ALL, ["out:spend_state_median", "out:spend_per_student"]),
    Q("who_better", "Which districts like {d} do better?", "comparison", HIGH,
      P_ALL, ["eco:who_does_better"]),
    Q("vs_neighbor", "Is {d} better than the district next door?", "comparison", HIGH,
      P_PUBLIC + ("board_trustee",),
      ["out:expectation.actual", "campus:district_rating", "eco:allocation.operating_per_student"],
      partial_ok=True),
    Q("vs_nation", "How does {d} compare to districts nationally?", "comparison", NORMAL,
      P_PRO, ["national:ppcs", "national:pctile"]),
    Q("tx_vs_states", "Does Texas spend more or less than other states?", "comparison", HIGH,
      P_PRO + ("taxpayer_voter",), ["cap:cross_state"]),
    Q("rank_debt", "Which Texas districts carry the most debt per student?",
      "exceptions", HIGH, P_PRO, ["cap:statewide_leaderboard"]),
    Q("rank_recapture", "Which districts pay the most recapture?", "exceptions", HIGH,
      P_PRO, ["cap:statewide_leaderboard"]),
    Q("rank_admin", "Which districts spend the most on administration?", "exceptions", HIGH,
      P_PRO, ["cap:statewide_leaderboard",
              "spend:functions.general_admin.per_student"]),

    # ---- outcomes ---------------------------------------------------------
    Q("staar", "How are {d}'s students doing on STAAR?", "current_status", CRITICAL,
      P_ALL, ["out:measures.test_all_meets"]),
    Q("grad", "What is {d}'s graduation rate?", "current_status", HIGH,
      P_ALL, ["out:measures.grad_rate_4yr"]),
    Q("attendance", "What is attendance like at {d}?", "current_status", NORMAL,
      P_ALL, ["out:measures.attendance_rate"]),
    Q("rating", "What is {d} rated by the state?", "current_status", CRITICAL,
      P_ALL, ["campus:district_rating", "campus:district_score"]),
    Q("worst_campus", "Are there failing schools inside {d}?", "exceptions", CRITICAL,
      P_PUBLIC + ("journalist", "board_trustee"),
      ["campus:campuses", "campus:worst", "campus:students_below_a_d"]),
    Q("my_school", "How is my child's specific school doing?", "current_status", CRITICAL,
      P_PUBLIC, ["cap:campus_ratings", "campus:campuses"]),
    Q("my_school_staar", "What are STAAR scores at my child's school?", "current_status",
      CRITICAL, P_PUBLIC, ["perf:subjects.all.meets", "perf:subjects.reading.meets",
                           "perf:subjects.math.meets"]),
    Q("staar_grade", "How did 4th graders in {d} do in math?", "current_status", HIGH,
      P_PUBLIC + ("journalist",), ["cap:staar_by_grade"]),
    Q("staar_race", "How do Black and Hispanic students do in {d}?", "comparison", HIGH,
      P_PRO + ("parent_resident",),
      ["perf:groups.african_american.meets", "perf:groups.hispanic.meets"]),
    Q("poor_students", "How do low-income students do in {d}?", "comparison", HIGH,
      P_ALL, ["equity:poor.meets"]),
    Q("sped_outcomes", "How do special education students do in {d}?", "comparison", HIGH,
      P_PRO + ("parent_resident",), ["equity:other_groups.special_ed"]),
    Q("beats_prediction", "Does {d} do better than its demographics predict?",
      "root_cause", HIGH, P_PRO, ["out:expectation.gap", "out:expectation.expected"]),
    Q("why_scores_low", "Why are {d}'s scores low?", "root_cause", HIGH, P_ALL,
      ["out:expectation.gap", "out:need.pct_econ_disadv",
       "perf:groups.econ_disadv.meets"],
      note="Gap vs prediction, need, and how the largest group actually scored."),

    # ---- teachers ---------------------------------------------------------
    Q("teacher_pay", "What do teachers earn in {d}?", "current_status", HIGH,
      P_ALL, ["out:measures.avg_teacher_salary"]),
    Q("turnover", "How many teachers leave {d} each year?", "current_status", HIGH,
      P_ALL, ["out:measures.teacher_turnover_pct"]),
    Q("class_size", "How big are classes in {d}?", "current_status", HIGH,
      P_PUBLIC, ["out:measures.students_per_teacher"]),
    Q("teacher_exp", "How experienced are {d}'s teachers?", "current_status", NORMAL,
      P_ALL, ["out:measures.teacher_avg_experience"]),
    Q("teacher_certified", "Are the teachers at my child's school certified?",
      "current_status", CRITICAL, P_PUBLIC, ["cap:teacher_certification"]),
    Q("campus_turnover", "Which schools in {d} lose the most teachers?", "exceptions",
      HIGH, P_PRO + ("parent_resident",),
      ["cap:campus_staff", "cap:campus_turnover"], partial_ok=True,
      note="Per-campus beginning-teacher share and tenure are published; TAPR "
           "does not publish campus-level turnover itself."),
    Q("raise_cost", "What would a 3% raise cost {d}?", "recommendation", HIGH,
      ("district_leader", "board_trustee"),
      ["eco:allocation.payroll_per_student", "cap:budget_forward"], partial_ok=True,
      note="Payroll per student supports an estimate; no adopted budget to apply it to."),

    # ---- debt and bonds ---------------------------------------------------
    Q("debt_total", "How much does {d} owe?", "financial", CRITICAL, P_ALL,
      ["debt:total", "debt:per_student"]),
    Q("debt_interest", "How much of {d}'s debt is interest?", "financial", HIGH,
      P_ALL, ["debt:interest_share_pct"]),
    Q("debt_clears", "When will {d}'s debt be paid off?", "forecast", HIGH,
      P_ALL, ["debt:clears_in"]),
    Q("debt_service", "How much does {d} pay on debt every year?", "financial", HIGH,
      P_ALL, ["forensic:outside_operating.per_student"]),
    Q("bond_history", "Has {d} passed a bond?", "historical", CRITICAL, P_ALL,
      ["bond:totals.props", "bond:totals.passed"]),
    Q("bond_last", "What was {d}'s last bond election?", "historical", HIGH,
      P_ALL, ["bond:elections"]),
    Q("bond_votes", "How did the vote split on {d}'s last bond?", "historical", NORMAL,
      P_PRO + ("taxpayer_voter",), ["bond:elections"]),
    Q("bond_athletics", "How much of {d}'s bond money went to athletics?", "financial",
      HIGH, P_PUBLIC + ("journalist",), ["bond:totals.athletics_asked"]),
    Q("bond_spent_on", "What exactly did {d} build with the last bond?", "historical",
      CRITICAL, P_ALL, ["cap:bond_projects"]),
    Q("bond_on_time", "Did {d}'s bond projects finish on budget?", "operations", HIGH,
      P_PRO + ("taxpayer_voter",), ["cap:bond_projects"]),
    Q("bond_worked", "Do bonds actually improve results?", "root_cause", NORMAL,
      P_PRO, ["cap:statewide_leaderboard"]),
    Q("should_i_vote", "Should I vote for {d}'s bond?", "recommendation", CRITICAL,
      P_PUBLIC + ("taxpayer_voter",),
      ["bond:totals.props", "debt:per_student", "cap:bond_projects"], partial_ok=True,
      note="History and current debt load are available; what the money buys is not."),

    # ---- trends -----------------------------------------------------------
    Q("trend_instruction", "Is {d} putting less into the classroom than it used to?",
      "trend", CRITICAL, P_ALL, ["trend:change.instruction_share"]),
    Q("trend_debt", "Has {d}'s debt burden grown?", "trend", HIGH, P_ALL,
      ["trend:change.debt_ps"]),
    Q("trend_security", "How much more is {d} spending on security?", "trend", NORMAL,
      P_ALL, ["trend:change.security_ps"]),
    Q("trend_enroll", "Is enrollment in {d} growing or shrinking?", "trend", HIGH,
      P_ALL, ["trend:series.enrollment"]),
    Q("trend_deficit", "Is {d} running a deficit?", "financial", CRITICAL, P_ALL,
      ["trend:change.operating_balance_ps"]),
    Q("trend_federal", "What happened when federal COVID money ran out in {d}?",
      "trend", HIGH, P_PRO, ["trend:change.federal_ps", "trend:series.federal_ps"]),
    Q("history_17y", "Show me {d}'s numbers back to 2009.", "historical", NORMAL,
      P_PRO, ["cap:time_series_17y", "trend:series.instruction_ps"]),

    # ---- forecasting / advice — the classic long tail ----------------------
    Q("enroll_forecast", "How many students will {d} have in five years?", "forecast",
      HIGH, P_PRO + ("realtor_relocating",), ["cap:enrollment_forecast"]),
    Q("close_schools", "Is {d} going to close any schools?", "forecast", CRITICAL,
      P_PUBLIC, ["cap:enrollment_forecast", "cap:budget_forward"]),
    Q("next_budget", "What is {d}'s budget for this year?", "current_status", CRITICAL,
      P_ALL, ["cap:budget_forward"]),
    Q("will_taxes_rise", "Will my school taxes go up next year?", "forecast", CRITICAL,
      P_PUBLIC, ["cap:budget_forward", "tax:change.rate_change_pct"], partial_ok=True,
      note="The rate's direction is published; next year's adopted rate is not."),
    Q("what_should_i_do", "What should {d} do to improve results?", "recommendation",
      HIGH, ("district_leader", "board_trustee"),
      ["out:expectation.gap", "eco:who_does_better"], partial_ok=True,
      note="The site shows who does better and by how much; it deliberately makes no "
           "per-district causal claim."),
    Q("cut_where", "Where can {d} cut without touching the classroom?", "recommendation",
      CRITICAL, ("district_leader", "board_trustee"),
      ["spend:functions.general_admin.per_student", "spend:functions.plant.per_student",
       "spend:functions.instruction.share_of_operating"]),

    # ---- operations, the detail people assume is there --------------------
    Q("admin_spend", "How much does {d} spend on administration?", "financial", CRITICAL,
      P_ALL, ["spend:functions.general_admin.per_student"]),
    Q("transport_spend", "What does {d} spend on buses?", "financial", HIGH,
      P_ALL, ["spend:functions.transportation.per_student"]),
    Q("food_spend", "What does {d} spend on school meals?", "financial", NORMAL,
      P_ALL, ["spend:functions.food.per_student"]),
    Q("counseling_spend", "Does {d} spend enough on counsellors?", "financial", HIGH,
      P_PUBLIC + ("board_trustee",),
      ["spend:functions.counseling.per_student", "spend:functions.counseling.percentile"]),
    Q("sped_spend", "How much does {d} spend on special education?", "financial",
      CRITICAL, P_ALL, ["spend:programs.special_ed.per_student"]),
    Q("athletics_spend", "How much does {d} spend on football?", "financial", HIGH,
      P_PUBLIC + ("journalist",),
      ["spend:programs.athletics.per_student"]),
    Q("supt_salary", "What is {d}'s superintendent paid?", "current_status", CRITICAL,
      P_PUBLIC + ("journalist",), ["cap:salaries_named"]),
    Q("vendors", "Who does {d} pay the most money to?", "operations", HIGH,
      P_PRO, ["cap:vendor_contracts"]),
    Q("reserves", "How much does {d} have in reserve?", "financial", CRITICAL,
      P_PRO + ("taxpayer_voter",), ["cap:fund_balance"]),
    Q("payroll_share", "How much of {d}'s spending is people versus things?",
      "financial", NORMAL, P_PRO,
      ["spend:objects.payroll.share", "spend:objects.supplies.share"]),
    Q("bilingual_spend", "What does {d} spend on bilingual and ESL students?",
      "financial", HIGH, P_ALL, ["spend:programs.bilingual.per_student"]),
    Q("compensatory_spend", "What does {d} spend on students at risk?", "financial",
      HIGH, P_PRO + ("parent_resident",),
      ["spend:programs.compensatory.per_student"]),
    Q("discipline", "How often are students suspended in {d}?", "operations", HIGH,
      P_PUBLIC + ("journalist",), ["cap:discipline_data"]),
    Q("under_investigation", "Is {d} under state investigation?", "current_status",
      CRITICAL, P_PRO + ("parent_resident",), ["cap:conservatorship"]),

    # ---- geography / relocation -------------------------------------------
    Q("which_district", "Which district am I in?", "geographic", CRITICAL,
      P_PUBLIC, ["geo:", "cap:campus_ratings"], partial_ok=True),
    Q("boundary", "Where are {d}'s boundaries?", "geographic", HIGH,
      P_PUBLIC, ["geo:"]),
    Q("which_school_zone", "Which elementary school would my address feed into?",
      "geographic", CRITICAL, P_PUBLIC, ["cap:attendance_zones"]),
    Q("best_nearby", "Which district near {d} is best for my kids?", "recommendation",
      CRITICAL, ("parent_resident", "realtor_relocating"),
      ["eco:who_does_better", "campus:district_rating", "out:expectation.gap"],
      partial_ok=True),
    Q("move_worth_it", "Is it worth moving to {d} for the schools?", "recommendation",
      HIGH, ("realtor_relocating", "parent_resident"),
      ["campus:district_rating", "eco:tax.bill_on_home", "out:measures.test_all_meets"],
      partial_ok=True),

    # ---- flags, anomalies, accountability ---------------------------------
    Q("flags", "Is anything unusual about {d}'s finances?", "exceptions", CRITICAL,
      P_ALL, ["forensic:flags"]),
    Q("debt_no_ballot", "Does {d} pay debt nobody voted on?", "exceptions", HIGH,
      P_PRO, ["forensic:ballot.props", "forensic:outside_operating.per_student"],
      partial_ok=True),
    Q("hidden_failing", "Does {d}'s rating hide failing campuses?", "exceptions",
      CRITICAL, P_ALL, ["campus:best", "campus:worst", "campus:spans_grades"]),
    Q("waste", "Is {d} wasting money?", "root_cause", CRITICAL, P_PUBLIC + ("journalist",),
      ["forensic:flags", "spend:functions.general_admin.percentile"], partial_ok=True,
      note="Published flags name a number against a threshold; the spend detail that "
           "would substantiate 'waste' is unreachable."),
    Q("corruption", "Has anyone at {d} been caught misusing funds?", "exceptions",
      CRITICAL, P_PUBLIC + ("journalist",), ["cap:vendor_contracts", "cap:conservatorship"]),

    # ---- research / access ------------------------------------------------
    Q("download", "Can I download all of this?", "operations", NORMAL, P_PRO,
      ["cap:raw_download"]),
    Q("api", "Is there an API?", "operations", NORMAL, P_PRO + ("vendor_prospect",),
      ["cap:api_access"]),
    Q("where_from", "Where does this number come from?", "operations", CRITICAL,
      P_ALL, ["cap:lineage"]),
    Q("methodology", "How was this calculated?", "operations", HIGH, P_ALL,
      ["cap:lineage"]),
    Q("spend_outcomes", "Does spending more actually improve results?", "root_cause",
      HIGH, P_PRO, ["cap:statewide_leaderboard", "out:expectation.model_r2"]),
    Q("ask_sql", "Which district had the biggest spending jump last year?",
      "exceptions", HIGH, P_PRO, ["cap:nl_query"]),
    Q("ask_sql_detail", "Which districts cut instruction while raising administration?",
      "exceptions", HIGH, P_PRO,
      ["cap:nl_query", "spend:functions.general_admin.share_first_year",
       "spend:functions.instruction.share_first_year"]),
    Q("charter_vs", "Do charters do better than {d} for less money?", "comparison",
      HIGH, P_ALL, ["cap:charter_comparison", "campus:district_rating"], partial_ok=True),
    Q("today", "What is happening at {d} right now?", "current_status", NORMAL,
      P_ALL, ["cap:current_year"]),

    # ---- ambiguous / malformed, because real people type like this --------
    Q("vague_money", "money", "ambiguous", NORMAL, P_PUBLIC,
      ["eco:allocation.total_per_student"], partial_ok=True,
      note="Resolvable to the district in context; the portal defaults to spend."),
    Q("vague_good", "is my district good", "ambiguous", HIGH, P_PUBLIC,
      ["campus:district_rating", "out:expectation.gap"], partial_ok=True),
    Q("misspelled", "how mch dose {d} spned per studnt", "ambiguous", NORMAL,
      P_PUBLIC, ["eco:allocation.total_per_student"]),
    Q("wrong_unit", "How much does {d} spend per school?", "ambiguous", NORMAL,
      P_PUBLIC, ["cap:campus_finance"]),
    Q("two_things", "Compare {d}'s debt and test scores over ten years.",
      "cross_system", HIGH, P_PRO,
      ["trend:series.debt_ps", "out:measures.test_all_meets"], partial_ok=True,
      note="Debt has 17 years; the outcome measure has 2 points, so the ten-year "
           "comparison cannot be drawn."),
    Q("outside_scope", "Can you help me enroll my child?", "out_of_scope", NORMAL,
      P_PUBLIC, ["cap:current_year"],
      note="Correctly outside what a finance portal should answer."),
]

CATEGORY_OF = {q["id"]: q["cat"] for q in QUESTIONS}


# --------------------------------------------------------------------------
# 4. RESOLUTION — grade one inquiry against the real data.
# --------------------------------------------------------------------------
def classify(cap: Capability, q: dict, district: str) -> dict:
    states, whys = [], []
    for spec in q["requires"]:
        st, why = cap.probe(district, spec)
        states.append(st)
        whys.append(f"{spec} -> {st}: {why}")

    present = sum(1 for s in states if s in ("PRESENT", "EXPLAINED"))
    total = len(states)
    unusable = [s for s in states if s == "UNUSABLE"]

    if present == total:
        grade, reason = "A", "every field the answer needs resolves for this district"
    elif unusable and present == 0:
        grade, reason = "D", "required data is held but no published surface exposes it"
    elif unusable:
        grade, reason = "D", "answer is blocked by data that exists but is unreachable"
    elif present == 0:
        grade, reason = "C", "none of the required data exists"
    elif q["partial_ok"]:
        grade, reason = "B", "part of the answer is supported; the rest is missing"
    else:
        grade, reason = "C", "a field the answer depends on is missing"

    return {"grade": grade, "reason": reason, "evidence": whys,
            "confidence": round(present / total, 2) if total else 0.0}


# --------------------------------------------------------------------------
# 5. THE SIMULATION
# --------------------------------------------------------------------------
def run_one(cap: Capability, seed: int, users: int, min_inquiries: int) -> dict:
    rng = random.Random(seed)

    # District sampling: enrollment^0.5 keeps the head realistic (people ask
    # about Houston more than about Loop ISD) without erasing the tail.
    pool = [d for d in cap.districts if cap.enrollment.get(d)]
    weights = [math.sqrt(cap.enrollment[d]) for d in pool]

    persona_names = list(PERSONAS)
    persona_w = [PERSONAS[p] for p in persona_names]

    by_grade = Counter()
    by_cat = defaultdict(Counter)
    by_persona = defaultdict(Counter)
    by_question = defaultdict(Counter)
    weighted = Counter()
    weighted_total = 0
    failures = Counter()
    examples = defaultdict(list)
    day_counts = Counter()
    inquiries = 0

    uid = 0
    while inquiries < min_inquiries or uid < users:
        uid += 1
        persona = rng.choices(persona_names, persona_w)[0]
        home = rng.choices(pool, weights)[0]
        lo, hi = DEPTH[persona]
        n_q = rng.randint(lo, hi)
        first_day = rng.randint(1, 90)
        eligible = [q for q in QUESTIONS if persona in q["personas"]]
        for _ in range(n_q):
            q = rng.choice(eligible)
            # Most questions are about the user's own district; pros roam.
            roam = 0.45 if persona in ("journalist", "policy_researcher") else 0.12
            district = rng.choices(pool, weights)[0] if rng.random() < roam else home
            day = min(90, first_day + rng.randint(0, 20))

            res = classify(cap, q, district)
            g = res["grade"]
            by_grade[g] += 1
            by_cat[q["cat"]][g] += 1
            by_persona[persona][g] += 1
            by_question[q["id"]][g] += 1
            day_counts[day] += 1
            w = q["importance"]
            weighted_total += w
            if g == "A":
                weighted["A"] += w
            elif g == "B":
                weighted["B"] += w
            weighted[g + "_all"] += w

            if g != "A":
                for line in res["evidence"]:
                    if "-> PRESENT" not in line and "-> EXPLAINED" not in line:
                        failures[line.split(" -> ")[0]] += 1
                if len(examples[g]) < 400:
                    examples[g].append({
                        "persona": persona, "district": cap.name.get(district, district),
                        "district_number": district,
                        "question": q["text"].replace("{d}", cap.name.get(district, district)),
                        "qid": q["id"], "category": q["cat"],
                        "importance": q["importance"], "grade": g,
                        "reason": res["reason"], "evidence": res["evidence"],
                        "note": q["note"],
                    })
            elif len(examples["A"]) < 200:
                examples["A"].append({
                    "persona": persona, "district": cap.name.get(district, district),
                    "question": q["text"].replace("{d}", cap.name.get(district, district)),
                    "qid": q["id"], "category": q["cat"], "grade": "A",
                    "evidence": res["evidence"],
                })
            inquiries += 1

    total = sum(by_grade.values())
    return {
        "seed": seed, "users": uid, "inquiries": total,
        "days_covered": len(day_counts),
        "grades": dict(by_grade),
        "full_rate": by_grade["A"] / total,
        "useful_rate": (by_grade["A"] + by_grade["B"]) / total,
        "weighted_full": weighted["A"] / weighted_total,
        "weighted_useful": (weighted["A"] + weighted["B"]) / weighted_total,
        "by_category": {k: dict(v) for k, v in by_cat.items()},
        "by_persona": {k: dict(v) for k, v in by_persona.items()},
        "by_question": {k: dict(v) for k, v in by_question.items()},
        "failures": dict(failures.most_common()),
        "examples": {k: v for k, v in examples.items()},
    }


def coverage_with(cap: Capability, granted: set[str], seeds: int, users: int,
                  inquiries: int) -> tuple[float, float]:
    """Re-run the simulation pretending `granted` capabilities exist.

    Counting how many questions a gap 'blocks' overstates it badly: most blocked
    questions need two or three things, so closing one gap alone converts
    nothing. The only honest measure of a fix is to re-run the whole simulation
    with it in place, which is what this does.
    """
    global GRANTED
    prev, GRANTED = GRANTED, granted
    try:
        runs = [run_one(cap, s, users, inquiries) for s in range(1, seeds + 1)]
    finally:
        GRANTED = prev
    return (statistics.mean(r["full_rate"] for r in runs),
            statistics.mean(r["weighted_full"] for r in runs))


def unlock_analysis(cap: Capability, baseline: float, seeds: int, users: int,
                    inquiries: int) -> list[dict]:
    """Marginal gain of closing each gap ON ITS OWN, by re-simulation."""
    fixable = [k for k, v in CAPABILITIES.items()
               if v["state"] in ("ABSENT", "UNUSABLE", "PARTIAL")]
    out = []
    for name in fixable:
        full, weighted = coverage_with(cap, {name}, seeds, users, inquiries)
        out.append({
            "capability": name,
            "state": CAPABILITIES[name]["state"],
            "coverage_alone": full,
            "gain_alone_pts": (full - baseline) * 100,
            "weighted_alone": weighted,
            "fix": CAPABILITIES[name].get("fix", ""),
            "evidence": CAPABILITIES[name]["evidence"],
        })
    out.sort(key=lambda r: -r["gain_alone_pts"])
    return out


def greedy_path(cap: Capability, baseline: float, target: float, seeds: int,
                users: int, inquiries: int) -> list[dict]:
    """Smallest set that clears the target, chosen one step at a time.

    Greedy is not guaranteed optimal, and this says so rather than claiming a
    minimum it did not prove.
    """
    fixable = {k for k, v in CAPABILITIES.items()
               if v["state"] in ("ABSENT", "UNUSABLE", "PARTIAL")}
    chosen: set[str] = set()
    current = baseline
    path = []
    while current < target and fixable:
        best, best_cov, best_w = None, current, 0.0
        for name in sorted(fixable):
            full, weighted = coverage_with(cap, chosen | {name}, seeds, users, inquiries)
            if full > best_cov:
                best, best_cov, best_w = name, full, weighted
        if best is None:
            break
        chosen.add(best)
        fixable.discard(best)
        path.append({
            "step": len(path) + 1,
            "add": best,
            "state": CAPABILITIES[best]["state"],
            "coverage_after": best_cov,
            "gain_pts": (best_cov - current) * 100,
            "weighted_after": best_w,
            "fix": CAPABILITIES[best].get("fix", ""),
        })
        current = best_cov
    return path


def grade_letter(pct: float) -> str:
    return ("A" if pct >= 0.90 else "B" if pct >= 0.80 else
            "C" if pct >= 0.70 else "D" if pct >= 0.60 else "F")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--inquiries", type=int, default=12000)
    ap.add_argument("--json", default="data/coverage_simulation.json")
    args = ap.parse_args()

    cap = Capability()
    print(f"capability map: {len(cap.districts)} districts, "
          f"{len(ARTIFACTS)} artefacts, {len(CAPABILITIES)} registered capabilities "
          f"({sum(1 for v in CAPABILITIES.values() if v['state'] == 'PRESENT')} present, "
          f"{sum(1 for v in CAPABILITIES.values() if v['state'] == 'UNUSABLE')} unusable, "
          f"{sum(1 for v in CAPABILITIES.values() if v['state'] == 'ABSENT')} absent)",
          file=sys.stderr)
    print(f"question bank: {len(QUESTIONS)} templates over "
          f"{len(set(q['cat'] for q in QUESTIONS))} categories", file=sys.stderr)

    runs = []
    for seed in range(1, args.seeds + 1):
        r = run_one(cap, seed, args.users, args.inquiries)
        runs.append(r)
        print(f"  seed {seed}: {r['users']:,} users, {r['inquiries']:,} inquiries, "
              f"full {r['full_rate']:.1%}, useful {r['useful_rate']:.1%}, "
              f"weighted {r['weighted_full']:.1%}", file=sys.stderr)

    full = [r["full_rate"] for r in runs]
    useful = [r["useful_rate"] for r in runs]
    wfull = [r["weighted_full"] for r in runs]

    def ci(xs):
        if len(xs) < 2:
            return (xs[0], xs[0])
        m, s = statistics.mean(xs), statistics.stdev(xs)
        h = 1.96 * s / math.sqrt(len(xs))
        return (m - h, m + h)

    base = runs[0]

    # The what-if passes re-run the whole simulation, so they use a smaller
    # sample for speed. The final set is re-verified at full size below.
    wu, wi = args.users // 4, max(3000, args.inquiries // 4)
    print("\n  measuring each gap on its own (re-simulation)…", file=sys.stderr)
    probe_base, _ = coverage_with(cap, set(), 2, wu, wi)
    unlocks = unlock_analysis(cap, probe_base, 2, wu, wi)
    for u in unlocks[:6]:
        print(f"    {u['capability']:24} +{u['gain_alone_pts']:.2f} pts alone",
              file=sys.stderr)

    print("\n  searching for the shortest path to 90%…", file=sys.stderr)
    path = greedy_path(cap, probe_base, 0.90, 2, wu, wi)
    for s in path:
        print(f"    {s['step']}. +{s['add']:24} -> {s['coverage_after']:.1%}",
              file=sys.stderr)

    final_set = {s["add"] for s in path}
    verified_full, verified_weighted = coverage_with(
        cap, final_set, args.seeds, args.users, args.inquiries)
    print(f"\n  verified at full sample: {verified_full:.1%} full, "
          f"{verified_weighted:.1%} weighted", file=sys.stderr)

    # Category rollup across all seeds.
    cats = defaultdict(Counter)
    for r in runs:
        for c, g in r["by_category"].items():
            cats[c].update(g)

    summary = {
        "methodology": {
            "seeds": args.seeds,
            "users_per_seed": args.users,
            "min_inquiries_per_seed": args.inquiries,
            "days": 90,
            "persona_mix": PERSONAS,
            "district_sampling": "enrollment^0.5 weighted, with 12% (public) / 45% (pro) "
                                 "roam off the user's own district",
            "question_templates": len(QUESTIONS),
            "grading": "A=every required field resolves; B=partial with a documented "
                       "substitute; C=data never collected; D=data held but no surface "
                       "exposes it",
            "absence_rule": "NOT_APPLICABLE and DID_NOT_HAPPEN count as answered; "
                            "NOT_MEASURED does not",
        },
        "full_answerability": statistics.mean(full),
        "full_ci95": ci(full),
        "useful_answerability": statistics.mean(useful),
        "useful_ci95": ci(useful),
        "business_weighted_full": statistics.mean(wfull),
        "business_weighted_ci95": ci(wfull),
        "grade": grade_letter(statistics.mean(full)),
        "grades_pooled": dict(sum((Counter(r["grades"]) for r in runs), Counter())),
        "by_category": {k: dict(v) for k, v in cats.items()},
        "by_persona": base["by_persona"],
        "by_question": base["by_question"],
        "top_blockers": unlocks,
        "path_to_90": path,
        "path_probe_baseline": probe_base,
        "path_verified": {
            "capabilities": sorted(final_set),
            "full_answerability": verified_full,
            "business_weighted": verified_weighted,
            "grade": grade_letter(verified_full),
        },
        "runs": [{k: v for k, v in r.items() if k != "examples"} for r in runs],
        "examples": base["examples"],
        "capability_registry": CAPABILITIES,
    }

    out = ROOT / args.json
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1))
    print(f"\nwrote {out} ({out.stat().st_size:,} bytes)", file=sys.stderr)

    print(f"\nFULL ANSWERABILITY   {statistics.mean(full):.1%}  "
          f"(95% CI {ci(full)[0]:.1%}–{ci(full)[1]:.1%})")
    print(f"USEFUL ANSWERABILITY {statistics.mean(useful):.1%}")
    print(f"BUSINESS-WEIGHTED    {statistics.mean(wfull):.1%}")
    print(f"GRADE                {grade_letter(statistics.mean(full))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

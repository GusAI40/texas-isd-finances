#!/usr/bin/env python3
"""STAAR at the campus, and results by student group at the district.

The campus layer already published a LETTER — A through F, one per campus. It
could not say what a campus's students actually scored, in which subject. And
the equity layer reports low-income students district-wide but no other group,
so "how do Black and Hispanic students do here" had no answer at all.

Both come from TAPR, which this repo has wanted for a while: `CLAUDE.md`
recorded the download as needing a human because the SAS broker's form
parameters were unmapped. They are mapped now — `scripts/ingest_tapr.py` walks
the wizard — and the one non-obvious part is `var_type`, which STAAR datasets
require and staff datasets do not. Without it the broker cheerfully returns a
200 containing nothing but campus names.

Which cut goes where follows the question, not the file:

**Campus gets SUBJECTS.** "What are the scores at my child's school" is about a
building, and reading against maths is the split a parent means.

**District gets STUDENT GROUPS.** "How do Black and Hispanic students do here"
is asked about a district, and campus-by-group cells are mostly masked anyway —
publishing them would be a table of blanks with a few identifiable children in
it.

Three refusals:

**A masked cell is not a zero and not a score.** TEA suppresses small groups to
protect identifiable students; those cells arrive EMPTY. Empty is omitted, so a
group with too few test-takers is absent rather than reported at 0%.

**Rates are published, never recomputed.** TEA's own numerator and denominator
are rounded before publication and dividing them back gives a slightly
different number than the one on TEA's page.

**No campus is ranked against a campus in another district.** The same rule
`tests/test_campuses.py` already enforces: a statewide campus league table is a
far more dangerous artefact than the gap inside one district, which is the
finding.

Usage:
    python scripts/ingest_tapr.py --download
    python scripts/build_campus_performance.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# TEA's own subject names -> our keys. Anything else in the file is ignored
# rather than guessed at.
SUBJECTS = {
    "All Subjects": "all",
    "Reading/Language Arts": "reading",
    "Mathematics": "math",
    "Science": "science",
    "Social Studies": "social_studies",
}

# The student groups worth publishing at district grain. Every one of these is
# a group people ask about by name; the file also carries inverse groups
# ("Non-Migrant") which say nothing on their own and are left out.
GROUPS = {
    "All Students": "all",
    "African American": "african_american",
    "Hispanic": "hispanic",
    "White": "white",
    "Asian": "asian",
    "American Indian": "american_indian",
    "Pacific Islander": "pacific_islander",
    "Two or More Races": "two_or_more",
    "Econ Disadv": "econ_disadv",
    "Special Ed (Current)": "special_ed",
    "EB/EL (Current)": "emergent_bilingual",
    "At Risk": "at_risk",
    "Gifted and Talented": "gifted",
    "Male": "male",
    "Female": "female",
}

MEASURES = {
    "# of Tests": "tests",
    "% At Approaches GL Standard or Above": "approaches",
    "% At Meets GL Standard or Above": "meets",
    "% At Masters GL Standard": "masters",
}

# Staff fields worth carrying per campus. Certification is deliberately NOT
# here: TAPR's staff dataset does not publish it, and a degree is not a
# certificate. Claiming otherwise would answer a parent's question with a
# different question's data.
STAFF = {
    "CPSTEXPA": ("teacher_experience_avg", "Average years a teacher has taught."),
    "CPSTTENA": ("teacher_tenure_avg", "Average years a teacher has been in THIS district."),
    "CPST00FP": ("beginning_teacher_pct", "Share of teachers in their first year."),
    "CPSTNOFP": ("no_degree_pct", "Share of teachers with no degree recorded."),
    "CPSTBAFP": ("bachelors_pct", "Share holding a bachelor's degree."),
    "CPSTMSFP": ("masters_pct", "Share holding a master's degree."),
    "CPSTPHFP": ("doctorate_pct", "Share holding a doctorate."),
    "CPSTTOSA": ("teacher_salary_avg", "Average base teacher salary."),
    "CPSTTOFC": ("teacher_fte", "Teachers, full-time equivalent."),
}


def read(path: Path) -> tuple[list[str], list[str], list[list[str]]]:
    with path.open(encoding="iso-8859-1", newline="") as fh:
        r = csv.reader(fh)
        labels = next(r)
        codes = next(r)
        return labels, codes, list(r)


def parse_label(label: str) -> tuple[str, str, str] | None:
    """('reading', 'hispanic', 'meets') from TEA's own prose header.

    Parsed from the LABEL rather than decoded from the column code. The codes
    are a positional cipher (CDH00AR01225R) and a decoder written by reading
    twelve examples is a decoder that is wrong about the thirteenth. The label
    states the subject, the group and the measure in words.
    """
    parts = [p.strip() for p in label.split(",")]
    if len(parts) < 5 or not parts[0].startswith("STAAR Performance"):
        return None
    subject = SUBJECTS.get(parts[1])
    group = GROUPS.get(parts[3])
    measure = MEASURES.get(parts[-1])
    if not (subject and group and measure):
        return None
    return subject, group, measure


def num(v: str) -> float | None:
    """A masked, absent or sentinel cell is None — never 0, never itself.

    TEA suppresses groups small enough to identify a child. Those cells arrive
    EMPTY, and an empty cell rendered as 0% would publish a failing score for a
    school that simply had four test-takers.

    TAPR ALSO uses NEGATIVE SENTINELS, which is the trap: the district file
    alone carries 115,038 cells of `-1` and 8,464 of `-3`. They parse as
    perfectly good floats, so a plain float() ships districts scoring "-1%" at
    the Meets bar. Neither a test count nor a percentage can be negative, so
    anything below zero is a code, not a measurement. This was caught by
    tests/test_provenance_layers.py before it reached an artefact, and the
    guard belongs here rather than in the caller.
    """
    v = (v or "").strip().replace("%", "").replace(",", "")
    if not v or v in {".", "*", "-", "n/a", "N/A"}:
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return None if f < 0 else f


def campus_subjects(path: Path) -> tuple[dict, int, int]:
    labels, codes, rows = read(path)
    wanted: dict[int, tuple[str, str, str]] = {}
    for i, lab in enumerate(labels):
        p = parse_label(lab)
        if p and p[1] == "all":            # campus grain: subjects only
            wanted[i] = p
    idx = {c: i for i, c in enumerate(codes)}
    out: dict[str, dict] = {}
    masked = kept = 0
    for row in rows:
        if len(row) < 4:
            continue
        campus = row[idx["CAMPUS"]].strip()
        district = row[idx["DISTRICT"]].strip()
        if not campus or not district:
            continue
        subs: dict[str, dict] = {}
        for i, (subject, _grp, measure) in wanted.items():
            if i >= len(row):
                continue
            v = num(row[i])
            if v is None:
                masked += 1
                continue
            kept += 1
            subs.setdefault(subject, {})[measure] = (
                int(v) if measure == "tests" else round(v, 1))
        subs = {k: v for k, v in subs.items() if v.get("tests")}
        if not subs:
            continue
        out[campus] = {
            "campus_name": row[idx["CAMPNAME"]].strip(),
            "district_number": district,
            "subjects": subs,
        }
    return out, masked, kept


def district_groups(path: Path) -> dict:
    labels, codes, rows = read(path)
    wanted = {i: p for i, lab in enumerate(labels) if (p := parse_label(lab))}
    idx = {c: i for i, c in enumerate(codes)}
    out: dict[str, dict] = {}
    for row in rows:
        if len(row) < 2:
            continue
        dn = row[idx["DISTRICT"]].strip()
        if not dn:
            continue
        groups: dict[str, dict] = {}
        subjects: dict[str, dict] = {}
        for i, (subject, group, measure) in wanted.items():
            if i >= len(row):
                continue
            v = num(row[i])
            if v is None:
                continue
            val = int(v) if measure == "tests" else round(v, 1)
            if subject == "all":
                groups.setdefault(group, {})[measure] = val
            if group == "all":
                subjects.setdefault(subject, {})[measure] = val
        groups = {k: v for k, v in groups.items() if v.get("tests")}
        subjects = {k: v for k, v in subjects.items() if v.get("tests")}
        if not groups and not subjects:
            continue
        out[dn] = {
            "district_name": row[idx["DISTNAME"]].strip(),
            "groups": groups,
            "subjects": subjects,
        }
    return out


def campus_staff(path: Path) -> dict:
    labels, codes, rows = read(path)
    idx = {c: i for i, c in enumerate(codes)}
    out: dict[str, dict] = {}
    for row in rows:
        if len(row) < 4:
            continue
        campus = row[idx["CAMPUS"]].strip()
        if not campus:
            continue
        rec = {}
        for code, (key, _why) in STAFF.items():
            i = idx.get(code)
            if i is None or i >= len(row):
                continue
            v = num(row[i])
            if v is not None:
                rec[key] = round(v, 1)
        if rec:
            out[campus] = rec
    return out


def build(camp_staar: Path, dist_staar: Path, camp_staff: Path) -> dict:
    campuses, masked, kept = campus_subjects(camp_staar)
    districts = district_groups(dist_staar)
    staff = campus_staff(camp_staff)

    for cnum, rec in campuses.items():
        if cnum in staff:
            rec["staff"] = staff[cnum]

    # Index campuses under their district so a district page loads one slice.
    by_district: dict[str, list[str]] = {}
    for cnum, rec in campuses.items():
        by_district.setdefault(rec["district_number"], []).append(cnum)

    state_groups: dict[str, dict] = {}
    for rec in districts.values():
        for g, m in rec["groups"].items():
            acc = state_groups.setdefault(g, {"tests": 0, "meets_n": 0.0})
            if m.get("tests") and m.get("meets") is not None:
                acc["tests"] += m["tests"]
                acc["meets_n"] += m["tests"] * m["meets"] / 100
    state = {g: {"tests": a["tests"],
                 "meets": round(a["meets_n"] / a["tests"] * 100, 1)}
             for g, a in state_groups.items() if a["tests"]}

    # The equity layer's statewide figure is an UNWEIGHTED mean across
    # districts (build_equity_data.py: frames["all"][BAR].mean()). That answers
    # "how does the typical DISTRICT do". The figure above is test-weighted and
    # answers "how does the typical STUDENT do" — 1,000 small districts must not
    # outvote Houston. On all students the two differ by about three points, so
    # both are published: a reader meeting both numbers should be able to see
    # why they differ instead of concluding one is wrong.
    unweighted: dict[str, list[float]] = {}
    for rec in districts.values():
        for g, m in rec["groups"].items():
            if m.get("meets") is not None and m.get("tests"):
                unweighted.setdefault(g, []).append(m["meets"])
    for g, vals in unweighted.items():
        if g in state:
            state[g]["meets_district_mean"] = round(sum(vals) / len(vals), 1)
            state[g]["districts_counted"] = len(vals)

    return {
        "meta": {
            "year": 2025,
            "school_year": "2024-25",
            "source": "Texas Academic Performance Report (TAPR)",
            "publisher": "Texas Education Agency",
            "campuses": len(campuses),
            "districts": len(districts),
            "campuses_with_staff": sum(1 for r in campuses.values() if "staff" in r),
            "masked_or_absent_cells": masked,
            "published_cells": kept,
            "bar": "Meets grade level or above, matching the equity layer",
            "limits": [
                "A masked cell is NOT a zero. TEA suppresses groups small enough "
                "to identify a student; those cells are omitted here, so a group "
                "missing from a campus or district had too few test-takers to "
                "report — it did not score nothing.",
                "Rates are TEA's published percentages, never recomputed from the "
                "numerator and denominator: TEA rounds before publishing and "
                "dividing them back gives a different number from the one on "
                "TEA's own page.",
                "Campus records carry SUBJECTS; student-group results are "
                "published at district grain only. Campus-by-group cells are "
                "mostly masked, and a table of blanks with a few identifiable "
                "children in it is worse than no table.",
                "No campus is ranked against a campus in another district. The "
                "finding is the spread INSIDE a district; a statewide campus "
                "league table is a far more dangerous artefact.",
                "Teacher CERTIFICATION is not published in TAPR's staff dataset "
                "and is not here. A degree is not a certificate, and the degree "
                "mix must not be presented as an answer to 'are the teachers "
                "certified'.",
                "Two statewide figures are published per group and they are not "
                "interchangeable. `meets` is test-weighted — the share of TEXAS "
                "TESTS that met the bar. `meets_district_mean` is the unweighted "
                "average of district rates, which is what the equity layer "
                "reports. On all students they read about 49.7% and 46.5%: the "
                "first says how the typical student did, the second how the "
                "typical district did, and neither is wrong.",
                "Campus-level teacher TURNOVER is likewise not in this dataset. "
                "Beginning-teacher share and average tenure are published "
                "instead, and they are related but not the same measure.",
            ],
        },
        "texas": {"groups": state},
        "districts": districts,
        "campuses": campuses,
        "campuses_by_district": by_district,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campus-staar", default="data/tapr_campus_staar_2025.csv")
    ap.add_argument("--district-staar", default="data/tapr_district_staar_2025.csv")
    ap.add_argument("--campus-staff", default="data/tapr_campus_staff_2025.csv")
    ap.add_argument("--out", default="static/campus_performance.json")
    args = ap.parse_args()

    paths = [ROOT / args.campus_staar, ROOT / args.district_staar,
             ROOT / args.campus_staff]
    for p in paths:
        if not p.exists():
            print(f"missing input: {p} — run scripts/ingest_tapr.py --download first",
                  file=sys.stderr)
            return 1

    payload = build(*paths)
    out = ROOT / args.out
    out.write_text(json.dumps(payload, separators=(",", ":")))
    m = payload["meta"]
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  {m['campuses']:,} campuses · {m['districts']:,} districts · "
          f"SY {m['school_year']}")
    print(f"  {m['campuses_with_staff']:,} campuses carry staff figures")
    print(f"  {m['published_cells']:,} cells published, "
          f"{m['masked_or_absent_cells']:,} masked or absent (omitted, never zero)")
    g = payload["texas"]["groups"]
    print("  statewide Meets, all subjects:")
    for k in ("all", "white", "asian", "hispanic", "african_american",
              "econ_disadv", "emergent_bilingual", "special_ed"):
        if k in g:
            print(f"    {k:<20} {g[k]['meets']:>5.1f}%  ({g[k]['tests']:,} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

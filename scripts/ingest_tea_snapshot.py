"""Ingest TEA Snapshot 'District and Charter Detail' into one tidy table.

The Snapshot files are the missing half of this project. Our PEIMS data says
where a district's money GOES. Snapshot says who its students ARE, what it pays
its teachers, how many of them quit, how wealthy its tax base is, and how its
students actually DID. Joined on district number and year, the two together
answer the question neither can answer alone: what does a dollar actually buy,
for whom, and under what conditions?

Source: https://rptsvr1.tea.texas.gov/perfreport/snapshot/download.html
  POST /perfreport/snapshot/push.cgi  level=district & set=<YY> & suf=.dat|.lyt

Why we map by DESCRIPTION and not by column name
------------------------------------------------
TEA embeds the reporting year in the variable name — the same measure is
DDA00A001S24R in 2024 and DDA00A001S18R in 2018, and the underlying test
changed name (TAKS → STAAR) partway through. Column names are therefore useless
as a stable key across 16 years. The .lyt layout file shipped with every year
gives a human description for each column, so we normalise on that text. When
TEA renames a variable again, this keeps working; when they change what a
measure MEANS, the description changes and the field drops out loudly rather
than silently carrying a different definition forward.

Every field below was read off the real layout files, not guessed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PUSH_CGI = "https://rptsvr1.tea.texas.gov/perfreport/snapshot/push.cgi"


def download(dest: Path, first: int, last: int) -> None:
    """Fetch snapshot .dat/.lyt pairs straight from TEA.

    data/*.csv is gitignored in this repo — datasets are regenerated, not
    committed — so the ingest has to be able to fetch its own inputs.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for year in range(first, last + 1):
        for suf in (".dat", ".lyt"):
            out = dest / f"snap{year}{suf}"
            if out.exists() and out.stat().st_size > 0:
                continue
            body = urllib.parse.urlencode(
                {"level": "district", "set": f"{year % 100:02d}", "suf": suf}).encode()
            req = urllib.request.Request(PUSH_CGI, data=body)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    out.write_bytes(r.read())
            except Exception as e:  # noqa: BLE001 - report and continue
                print(f"  ! {year}{suf}: {e}", file=sys.stderr)
                continue
        print(f"  downloaded {year}")

# canonical field -> pattern matched against the .lyt DESCRIPTION (upper-cased).
# Order matters: the first column whose description matches wins.
FIELDS: dict[str, str] = {
    # --- identity -------------------------------------------------------
    "district_number":       r"^(COUNTY-)?DISTRICT NUMBER$",
    "district_name":         r"^DISTRICT NAME$",
    "county":                r"^COUNTY NUMBER AND NAME$",
    "region":                r"^EDUCATION SERVICE CENTER REGION$",
    "campuses":              r"^TOTAL NUMBER OF SCHOOLS$",
    # --- who the students are -------------------------------------------
    "students":              r"^TOTAL STUDENTS$",
    "pct_econ_disadv":       r"% ECONOMICALLY DISADVANTAGED",
    "pct_emergent_bilingual": r"% (ENGLISH LEARNERS|ENGLISH LANGUAGE LEARNERS|LIMITED ENGLISH)",
    "pct_special_ed":        r"% SPECIAL EDUCATION",
    "pct_bilingual_esl":     r"% BILINGUAL/ESL",
    "pct_career_tech":       r"% (CAREER & TECHNICAL|CAREER AND TECHNICAL)",
    "pct_gifted":            r"% GIFTED",
    "pct_hispanic":          r"^STUDENTS: % HISPANIC$",
    "pct_african_american":  r"^STUDENTS: % AFRICAN AMERICAN$",
    "pct_white":             r"^STUDENTS: % WHITE$",
    "pct_asian":             r"^STUDENTS: % ASIAN$",
    # --- the teaching workforce -----------------------------------------
    "staff_fte":             r"^TOTAL STAFF FTE$",
    "teacher_fte":           r"^TOTAL TEACHER FTE$",
    "avg_teacher_salary":    r"^AVERAGE SALARY: TEACHER$",
    "students_per_teacher":  r"NUMBER OF STUDENTS PER TEACHER",
    "teacher_turnover_pct":  r"TEACHER: TURNOVER RATE",
    "teacher_avg_experience": r"TEACHER: AVERAGE YEARS OF EXPERIENCE",
    "pct_teachers_new":      r"TEACHER: % WITH 5 OR FEWER YEARS",
    "pct_teachers_advanced_degree": r"TEACHER: % WITH ADVANCED DEGREES",
    "pct_staff_teachers":    r"^STAFF: % TEACHERS$",
    # --- the tax base and the money in --------------------------------
    "taxable_value_per_pupil": r"TAXABLE VALUE PER PUPIL",
    "tax_rate":              r"LOCALLY ADOPTED TAX RATE",
    "pct_revenue_state":     r"REVENUE: % STATE",
    "pct_revenue_federal":   r"REVENUE: % FEDERAL",
    "pct_revenue_local":     r"REVENUE: % LOCAL",
    "fund_balance":          r"^FUND BALANCE",
    "pct_spend_instruction": r"EXPENDITURE: % INSTRUCTIONAL",
    "instruction_per_pupil": r"TOTAL ACTUAL INSTRUCTIONAL EXPENDITURES PER PUPIL",
    "operating_per_pupil":   r"TOTAL ACTUAL OPERATING EXPENDITURES PER PUPIL",
    # --- what actually happened to students -----------------------------
    "accountability_rating": r"DISTRICT ACCOUNTABILITY RATINGS",
    "attendance_rate":       r"^ATTENDANCE RATE",
    "dropout_rate":          r"ANNUAL DROPOUT RATE GR\. 9-12",
    "grad_rate_4yr":         r"(4-YR )?LONGITUDINAL GRADUATION RATE",
    "graduates":             r"^ANNUAL GRADUATE COUNT",
    # 2018+ reports "AT APPROACHES GRADE LEVEL"; 2013-17 reported a bare
    # phase-in satisfactory rate. Both land here, and `test_standard` records
    # which definition each row used so nobody compares across the break blind.
    "test_all_approaches":   r"STAAR.*ALL SUBJECTS AT (APPROACHES|LEVEL II)|^STAAR: % ALL SUBJECTS$",
    "test_all_meets":        r"STAAR.*ALL SUBJECTS AT MEETS",
    "test_all_masters":      r"STAAR.*ALL SUBJECTS AT MASTERS",
    "test_reading_meets":    r"STAAR.*(ELA/READING|READING).*AT MEETS",
    "test_math_meets":       r"STAAR.*MATH.*AT MEETS",
}

# Percentages TEA stores as whole numbers; salaries/values as dollars. Anything
# here that arrives as a string with a comma or dollar sign is cleaned below.
LYT_ROW = re.compile(r"^\s*(\d+)\s+(\S+)\s+(Character|Numeric)\s+(\d+)\s+(.*?)\s*$")


def parse_layout(path: Path) -> dict[str, str]:
    """.lyt -> {column_name: DESCRIPTION}"""
    out = {}
    for line in path.read_text(errors="ignore").splitlines():
        m = LYT_ROW.match(line)
        if m:
            out[m.group(2)] = m.group(5).upper()
    return out


def build_map(layout: dict[str, str]) -> dict[str, tuple[str, str]]:
    """canonical field -> (actual column name, its description) for this year."""
    mapping = {}
    for field, pattern in FIELDS.items():
        rx = re.compile(pattern)
        for col, desc in layout.items():
            if rx.search(desc):
                mapping[field] = (col, desc)
                break
    return mapping


def clean(v: str):
    v = (v or "").strip().strip('"')
    # TEA masks values it cannot publish under FERPA. A masked cell is missing
    # data, not zero — writing 0 here would silently invent a real measurement.
    if v in ("", ".", "-1", "-3", "*", "N/A", "n/a"):
        return None
    v = v.replace(",", "").replace("$", "").replace("%", "")
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() and abs(f) < 2**53 else f


def ingest_year(dat: Path, lyt: Path, year: int) -> tuple[list[dict], dict]:
    layout = parse_layout(lyt)
    mapping = build_map(layout)
    # TEA changed the passing standard mid-series. Record which one each row
    # used rather than letting a chart imply one continuous measure.
    tdesc = mapping.get("test_all_approaches", ("", ""))[1]
    standard = ("approaches_grade_level" if "APPROACHES" in tdesc or "LEVEL II" in tdesc
                else "phase_in_satisfactory" if tdesc else None)
    rows, reader = [], csv.DictReader(dat.open(errors="ignore"))
    for raw in reader:
        rec = {"year": year}
        for field, (col, _desc) in mapping.items():
            rec[field] = clean(raw.get(col))
        rec["test_standard"] = standard
        num = rec.get("district_number")
        if not num:
            continue
        # district_number is a 6-digit string; leading zeros are load-bearing
        rec["district_number"] = str(num).zfill(6)
        rows.append(rec)
    missing = [f for f in FIELDS if f not in mapping]
    return rows, {"year": year, "rows": len(rows), "mapped": len(mapping),
                  "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="dir holding snapYYYY.dat/.lyt")
    ap.add_argument("--out", required=True, help="output CSV path")
    ap.add_argument("--report", help="write a JSON coverage report here")
    ap.add_argument("--download", action="store_true",
                    help="fetch the source files from TEA into --src first")
    ap.add_argument("--from-year", type=int, default=2009)
    ap.add_argument("--to-year", type=int, default=2024)
    args = ap.parse_args()

    src = Path(args.src)
    if args.download:
        print(f"Downloading TEA Snapshot {args.from_year}-{args.to_year} into {src}")
        download(src, args.from_year, args.to_year)
        print()
    all_rows, reports = [], []
    for dat in sorted(src.glob("snap*.dat")):
        year = int(re.search(r"(\d{4})", dat.name).group(1))
        lyt = dat.with_suffix(".lyt")
        if not lyt.exists():
            print(f"  ! {dat.name}: no layout file, skipped", file=sys.stderr)
            continue
        rows, rep = ingest_year(dat, lyt, year)
        all_rows += rows
        reports.append(rep)
        miss = f"  missing: {', '.join(rep['missing'])}" if rep["missing"] else ""
        print(f"  {year}: {rep['rows']:>5} districts, {rep['mapped']}/{len(FIELDS)} fields{miss}")

    if not all_rows:
        print("No rows ingested.", file=sys.stderr)
        return 1

    cols = ["year"] + list(FIELDS) + ["test_standard"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nWrote {len(all_rows):,} district-years to {out}")

    if args.report:
        Path(args.report).write_text(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

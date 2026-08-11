"""Campus-level accountability ratings, from TEA's own statewide summary.

The gap this fills
------------------
Every figure on this site stops at the district. That is where the money is
reported and it is the wrong unit for the question a family actually asks,
because a district rating is an average and an average hides its own tails.
A district the state rates B can contain a campus the state rates F, and the
child goes to the campus, not to the average.

TEA publishes the campus ratings in one first-party workbook — the Enhanced
Statewide Summary — which carries every district AND every campus for the
current year with demographics, plus a longitudinal sheet back to 2011. This
extracts the current-year rows to a flat CSV.

Two distinctions that must survive the extraction
-------------------------------------------------
"Not Rated" is NOT a bad rating. 525 campuses have no rating for the year —
too few students, a first year of operation, a data issue. Treating that as
failure would manufacture 525 failing schools out of missing data, which is
the same error the absence layer exists to prevent.

Alternative Education Accountability campuses are rated on a different scale.
They serve students who have been removed from, or are at risk of leaving, a
regular campus, and holding them to the regular standard would be a
comparison nobody makes on purpose. The flag is carried so downstream code can
exclude them; it turns out only 2 of the 223 headline campuses carry it, so
the finding does not depend on the choice — but it has to be visible.

    python scripts/ingest_tea_accountability.py
    python scripts/ingest_tea_accountability.py --keep-workbook

Source: https://tea.texas.gov/.../2025-enhanced-statewide-summary.xlsx
"""
from __future__ import annotations

import argparse
import ssl
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
YEAR = 2025
URL = ("https://tea.texas.gov/texas-schools/accountability/academic-accountability/"
       f"performance-reporting/{YEAR}-enhanced-statewide-summary.xlsx")
SHEET = f"{YEAR} State Summary"
UA = "txisd-accountability-ingest/1.0 (+https://txisd.dev/sources)"

# The workbook writes headers with embedded newlines ("District\nNumber").
KEEP = {
    "District Number": "district_number", "District": "district_name",
    "Campus Number": "campus_number", "Campus": "campus_name",
    "Region": "region", "County": "county", "School Type": "school_type",
    "Grades Served": "grades_served",
    "Alternative Education Accountability": "is_aea",
    "Charter": "is_charter", "Number of Students": "students",
    "% Economically Disadvantaged": "pct_poor", "% EB/EL Students": "pct_eb_el",
    "Overall Rating": "rating", "Overall Score": "score",
    "Student Achievement Rating": "achievement_rating",
    "Student Achievement Score": "achievement_score",
    "School Progress Rating": "progress_rating",
    "School Progress Score": "progress_score",
    "Closing the Gaps Rating": "gaps_rating",
    "Closing the Gaps Score": "gaps_score",
}
MIN_CAMPUSES = 8000        # 9,084 when written; a big drop means the sheet moved


def download(dest: Path) -> Path:
    if dest.exists():
        print(f"  using cached {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"  downloading {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180,
                                context=ssl.create_default_context()) as r:
        dest.write_bytes(r.read())
    print(f"  {dest.stat().st_size:,} bytes")
    return dest


def extract(xlsx: Path) -> pd.DataFrame:
    d = pd.read_excel(xlsx, sheet_name=SHEET, dtype=str)
    d.columns = [c.replace("\n", " ").strip() for c in d.columns]
    missing = [c for c in KEEP if c not in d.columns]
    if missing:
        raise SystemExit(f"the workbook no longer has: {missing}")
    d = d[list(KEEP)].rename(columns=KEEP)

    # The sheet interleaves one district row with its campus rows; the campus
    # number is what tells them apart.
    d["campus_number"] = d.campus_number.fillna("").str.strip()
    d["is_district_row"] = d.campus_number == ""
    for c in ("students", "score", "achievement_score", "progress_score",
              "gaps_score", "pct_poor", "pct_eb_el"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("is_aea", "is_charter"):
        d[c] = d[c].astype(str).str.strip().str.upper().eq("YES")
    d["year"] = YEAR
    return d


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data/tea_accountability.csv")
    ap.add_argument("--workbook", type=Path,
                    default=ROOT / "data/tea_accountability_summary.xlsx")
    ap.add_argument("--keep-workbook", action="store_true")
    args = ap.parse_args()

    print(f"TEA Enhanced Statewide Summary, {YEAR}")
    xlsx = download(args.workbook)
    d = extract(xlsx)

    campuses = int((~d.is_district_row).sum())
    if campuses < MIN_CAMPUSES:
        raise SystemExit(f"refusing: only {campuses} campus rows, expected "
                         f">= {MIN_CAMPUSES}. The sheet layout has changed.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(args.out, index=False)
    if not args.keep_workbook:
        xlsx.unlink(missing_ok=True)

    rated = d[~d.is_district_row]
    print(f"\nwrote {args.out.relative_to(ROOT)} — {len(d):,} rows "
          f"({campuses:,} campuses, {int(d.is_district_row.sum()):,} districts)")
    print(f"  ratings: {rated.rating.value_counts().to_dict()}")
    print(f"  'Not Rated' is not a bad rating — {int((rated.rating == 'Not Rated').sum())} "
          f"campuses, excluded from every count downstream")
    print(f"  alternative-education campuses flagged: {int(rated.is_aea.sum())}")
    print("next: python scripts/build_campus_data.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

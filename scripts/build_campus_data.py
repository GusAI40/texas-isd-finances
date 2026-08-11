"""What the district rating hides: the campuses inside it.

Everything else on this site is measured at the district. That is where money
is reported, and it is the wrong unit for the question a family asks, because a
district rating is an average over campuses and an average hides its own tails.

The finding
-----------
**138,664 Texas students attend a campus the state rates D or F inside a
district the state rates A or B.** 221 campuses, 73 districts. 21,415 of those
students are at a campus rated F.

And the spread is the rule rather than the exception: of the 890 districts with
more than one rated campus, 779 (88%) contain campuses at different letter
grades, and 196 span three or more. "The district is a B" is a true statement
that describes almost nobody's school.

This is not an accusation. A large district containing a struggling campus is
arithmetic, not misconduct, and no district chooses its students. What it is,
is a fact the district-level number cannot express — which is the whole reason
to publish it.

Three refusals
--------------
- "Not Rated" is not a bad rating. 525 campuses carry it and every one is
  excluded. Counting them as failure would manufacture 525 failing schools out
  of missing data.
- Alternative Education Accountability campuses are rated on a different scale
  and are excluded from the headline. Only 2 of the 223 raw matches carry the
  flag, so the finding does not depend on the choice — but a reader should not
  have to take that on trust, so both figures ship.
- No campus is ranked against a campus in another district on this page. The
  claim is about the GAP INSIDE a district, which is the thing a district
  rating conceals; a statewide campus league table is a different and much
  more dangerous artefact.

    python scripts/build_campus_data.py

Source: scripts/ingest_tea_accountability.py (tea.texas.gov, first-party).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
YEAR = 2025
GRADE = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
GOOD, POOR = 3, 1          # district rated A/B; campus rated D/F
TOP_N = 25


def load(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(path, dtype={"district_number": str, "campus_number": str},
                    low_memory=False)
    d["is_district_row"] = d.is_district_row.astype(str).str.upper().eq("TRUE")
    for c in ("is_aea", "is_charter"):
        d[c] = d[c].astype(str).str.upper().eq("TRUE")
    districts = d[d.is_district_row].set_index("district_number")
    campuses = d[~d.is_district_row].copy()
    campuses["grade"] = campuses.rating.map(GRADE)
    campuses["district_rating"] = campuses.district_number.map(districts.rating)
    campuses["district_grade"] = campuses.district_rating.map(GRADE)
    return districts, campuses


def build(src: Path, out: Path) -> dict:
    districts, camp = load(src)
    # Rated campuses only. "Not Rated" is missing data, not a low score.
    rated = camp.dropna(subset=["grade", "students"]).copy()
    scored = rated.dropna(subset=["district_grade"])

    raw = scored[(scored.district_grade >= GOOD) & (scored.grade <= POOR)]
    hidden = raw[~raw.is_aea]
    failing = hidden[hidden.grade == 0]

    spread = (scored.groupby("district_number")
              .agg(n=("grade", "size"), lo=("grade", "min"), hi=("grade", "max")))
    multi = spread[spread.n >= 2]

    by_district = (hidden.groupby("district_number")
                   .agg(students=("students", "sum"), campuses=("campus_name", "size"))
                   .sort_values("students", ascending=False))

    def district_row(num: str) -> dict:
        d = districts.loc[num]
        return {"district_number": num, "district_name": d.district_name,
                "district_rating": d.rating}

    payload = {
        "meta": {
            "source": "tea_accountability",
            "publisher": "Texas Education Agency",
            "year": YEAR,
            "campuses_rated": int(len(rated)),
            "campuses_not_rated": int((camp.rating == "Not Rated").sum()),
            "districts": int(scored.district_number.nunique()),
            "what_this_is": "The A-F rating the state gives each campus, set "
                            "against the rating it gives the district that "
                            "campus belongs to.",
            "what_this_is_not": "None of this is an accusation. A large district "
                                "containing a struggling campus is arithmetic, "
                                "not misconduct, and no district chooses its "
                                "students. It is a fact the district-level "
                                "number cannot express.",
            "limits": [
                f"'Not Rated' is not a bad rating. {int((camp.rating == 'Not Rated').sum())} "
                f"campuses carry it — too few students, a first year of operation, "
                f"a data issue — and every one is excluded rather than counted as "
                f"failure.",
                "Alternative Education Accountability campuses are rated on a "
                "different scale and are excluded from the headline. Both figures "
                "are published so the choice is visible rather than trusted.",
                "No campus is ranked against a campus in another district here. "
                "The claim is about the gap INSIDE a district, which is what a "
                "district rating conceals.",
                f"One year ({YEAR}). A single campus rating moves on small numbers "
                "of students and should not be read as a trend.",
                "A rating is a measure of tested performance against state "
                "targets, not of a school.",
            ],
        },
        "texas": {
            "rating_counts": {k: int(v) for k, v in
                              camp.rating.value_counts().items()},
            "hidden_by_the_district_average": {
                "campuses": int(len(hidden)),
                "students": int(hidden.students.sum()),
                "districts": int(hidden.district_number.nunique()),
                "rated_f": {"campuses": int(len(failing)),
                            "students": int(failing.students.sum())},
                "including_alternative_education": {
                    "campuses": int(len(raw)),
                    "students": int(raw.students.sum())},
                "reading": (
                    f"{int(hidden.students.sum()):,} students attend a campus "
                    f"Texas rates D or F inside a district Texas rates A or B."),
                "largest": [
                    {**district_row(num), "campuses": int(r.campuses),
                     "students": int(r.students)}
                    for num, r in by_district.head(TOP_N).iterrows()],
            },
            "spread": {
                "districts_with_two_or_more_rated_campuses": int(len(multi)),
                "campuses_differ": int((multi.hi > multi.lo).sum()),
                "campuses_differ_pct": round(100 * float((multi.hi > multi.lo).mean()), 1),
                "span_three_or_more_grades": int((multi.hi - multi.lo >= 3).sum()),
                "reading": (
                    f"{int((multi.hi > multi.lo).sum()):,} of {len(multi):,} districts "
                    f"with more than one rated campus contain campuses at different "
                    f"letter grades. 'The district is a B' describes almost nobody's "
                    f"school."),
            },
        },
        "districts": {},
    }

    for num, g in rated.groupby("district_number"):
        d = districts.loc[num] if num in districts.index else None
        rows = sorted(
            ({"campus_number": c.campus_number, "campus_name": c.campus_name,
              "school_type": c.school_type, "students": int(c.students),
              "pct_poor": round(float(c.pct_poor) * 100, 1) if pd.notna(c.pct_poor) else None,
              "rating": c.rating,
              "score": int(c.score) if pd.notna(c.score) else None,
              "is_alternative_education": bool(c.is_aea)}
             for c in g.itertuples()),
            key=lambda r: (GRADE.get(r["rating"], 9), -r["students"]))
        # `rows` is sorted worst-first, and unrated campuses sort last because
        # GRADE.get(..., 9) puts them beyond an A. Taking rows[0]/rows[-1] as
        # best/worst therefore reads the list backwards AND can report "Not
        # Rated" as a district's best campus. Derive both from the grades.
        grades = [GRADE[r["rating"]] for r in rows if r["rating"] in GRADE]
        letter = {v: k for k, v in GRADE.items()}
        below = [r for r in rows if GRADE.get(r["rating"], 9) <= POOR
                 and not r["is_alternative_education"]]
        payload["districts"][num] = {
            "district_name": d.district_name if d is not None else num,
            "district_rating": d.rating if d is not None else None,
            "district_score": (int(d.score) if d is not None and pd.notna(d.score)
                               else None),
            "campuses": rows,
            "best": letter[max(grades)] if grades else None,
            "worst": letter[min(grades)] if grades else None,
            "spans_grades": (max(grades) - min(grades)) if grades else 0,
            "students_below_a_d": sum(r["students"] for r in below),
        }

    out.write_text(json.dumps(payload, separators=(",", ":")))
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=ROOT / "data/tea_accountability.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "static/campus_data.json")
    args = ap.parse_args()

    p = build(args.src, args.out)
    t, h, s = p["texas"], p["texas"]["hidden_by_the_district_average"], p["texas"]["spread"]
    print(f"wrote {args.out.relative_to(ROOT)} — {p['meta']['campuses_rated']:,} rated "
          f"campuses in {p['meta']['districts']:,} districts, "
          f"{args.out.stat().st_size / 1024:,.0f} KB\n")
    print(f"  ratings: {t['rating_counts']}")
    print(f"\n  {h['reading']}")
    print(f"    {h['campuses']} campuses, {h['districts']} districts")
    print(f"    of those rated F: {h['rated_f']['campuses']} campuses, "
          f"{h['rated_f']['students']:,} students")
    print(f"\n  {s['reading']}")
    print(f"    spanning three or more grades: {s['span_three_or_more_grades']}")
    print("\n  largest:")
    for r in h["largest"][:6]:
        print(f"    {r['district_name'][:28]:<30} rated {r['district_rating']}  "
              f"{r['campuses']:>2} D/F campuses, {r['students']:>6,} students")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

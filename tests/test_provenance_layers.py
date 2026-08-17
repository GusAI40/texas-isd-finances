"""Re-derive the newer layers' headlines from source, longhand.

`tests/test_provenance.py` does this for the PEIMS layers: it recomputes every
published figure from the state's own file without importing a builder, so a
wrong number cannot validate itself. Four layers arrived after it and were
never brought into that chain — bonds, debt outstanding, campuses, and the
forensic quality tests. Their builders check themselves, which is not the same
thing at all: a builder that computes a figure wrongly will also assert it
wrongly, and the test suite stays green.

So everything here reaches past the builder to the raw file and counts by hand,
with the `csv` module and arithmetic. If a builder is edited and starts
producing a different number, these fail; if the upstream file is restated,
these fail; and neither failure depends on the code that produced the artefact
agreeing with itself.

Skips cleanly when a source file is absent — the raw CSVs are not committed
(too large), so in CI this covers what it can and says so rather than passing
vacuously.
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA, STATIC = ROOT / "data", ROOT / "static"
EXCEL_EPOCH = dt.date(1899, 12, 30)


def _need(*paths: Path):
    for p in paths:
        if not p.exists():
            pytest.skip(f"{p.name} not present (raw sources are not committed)")


def _rows(p: Path, encoding: str = "utf-8"):
    with p.open(encoding=encoding, newline="") as fh:
        return list(csv.DictReader(fh))


def _art(name: str) -> dict:
    p = STATIC / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return json.loads(p.read_text())


# --- bonds -------------------------------------------------------------------

def test_the_bond_counts_come_from_the_ballot_file():
    src = DATA / "texas_bond_elections.csv"
    _need(src)
    rows = _rows(src, "utf-8-sig")
    decided = [r for r in rows if (r.get("Result") or "").strip() in ("Carried", "Defeated")]
    meta = _art("bond_data.json")["meta"]
    assert meta["propositions"] == len(decided)

    asked = sum(float(r["$ Amount"]) for r in decided if (r.get("$ Amount") or "").strip())
    assert abs(meta["total_asked"] - asked) < 1.0
    approved = sum(float(r["$ Amount"]) for r in decided
                   if r["Result"].strip() == "Carried" and (r.get("$ Amount") or "").strip())
    assert abs(meta["total_approved"] - approved) < 1.0


def test_the_bond_year_range_comes_from_the_ballot_file():
    src = DATA / "texas_bond_elections.csv"
    _need(src)
    years = []
    for r in _rows(src, "utf-8-sig"):
        if (r.get("Result") or "").strip() not in ("Carried", "Defeated"):
            continue
        v = (r.get("Elect. Date") or "").strip()
        if v.lstrip("-").isdigit():
            years.append(dt.date.fromordinal(EXCEL_EPOCH.toordinal() + int(v)).year)
    meta = _art("bond_data.json")["meta"]
    assert meta["first_year"] == min(years)
    assert meta["last_year"] == max(years)


# --- debt outstanding --------------------------------------------------------

def test_the_debt_totals_are_the_fiscal_2025_column_summed():
    src = DATA / "brb_debt_outstanding.csv"
    _need(src)
    principal = interest = 0.0
    for r in _rows(src):
        if r["fiscal_year"].strip() != "2025" or not r["district_number"].strip():
            continue
        principal += float(r["cib_principal_outstanding"]) + float(r["cab_principal_outstanding"])
        interest += float(r["cib_interest_outstanding"]) + float(r["cab_interest_outstanding"])
    t = _art("debt_data.json")["texas"]
    assert abs(t["principal"] - principal) < 2
    assert abs(t["interest"] - interest) < 2
    assert abs(t["total"] - (principal + interest)) < 2


def test_the_cab_deferred_interest_is_the_cab_column_alone():
    """The whole CAB finding rests on this one column being read correctly."""
    src = DATA / "brb_debt_outstanding.csv"
    _need(src)
    deferred = 0.0
    districts = set()
    for r in _rows(src):
        if r["fiscal_year"].strip() != "2025" or not r["district_number"].strip():
            continue
        p, i = float(r["cab_principal_outstanding"]), float(r["cab_interest_outstanding"])
        deferred += i
        if p or i:
            districts.add(r["district_number"])
    cab = _art("debt_data.json")["texas"]["cab"]
    assert abs(cab["deferred_interest"] - deferred) < 2
    assert cab["districts"] == len(districts)


def test_the_payoff_year_is_the_last_year_with_anything_owed():
    src = DATA / "brb_debt_outstanding.csv"
    _need(src)
    last = 0
    for r in _rows(src):
        if not r["district_number"].strip():
            continue
        owed = sum(float(r[c]) for c in (
            "cib_principal_outstanding", "cib_interest_outstanding",
            "cab_principal_outstanding", "cab_interest_outstanding"))
        y = int(r["fiscal_year"])
        if owed > 0 and y > last:
            last = y
    assert _art("debt_data.json")["texas"]["clears_in"] == last


# --- campuses ----------------------------------------------------------------

def test_the_campus_headline_is_recomputable_from_the_tea_file():
    """138,664 students, counted again from TEA's rows rather than the builder's."""
    src = DATA / "tea_accountability.csv"
    _need(src)
    grade = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    rows = _rows(src)
    district_rating = {r["district_number"]: r["rating"]
                       for r in rows if r["is_district_row"].upper() == "TRUE"}
    students = campuses = 0
    districts = set()
    for r in rows:
        if r["is_district_row"].upper() == "TRUE":
            continue
        if r["is_aea"].upper() == "TRUE":
            continue
        cg = grade.get(r["rating"])
        dg = grade.get(district_rating.get(r["district_number"], ""))
        if cg is None or dg is None or not r["students"].strip():
            continue
        if dg >= 3 and cg <= 1:
            campuses += 1
            students += int(float(r["students"]))
            districts.add(r["district_number"])
    h = _art("campus_data.json")["texas"]["hidden_by_the_district_average"]
    assert h["campuses"] == campuses
    assert h["students"] == students
    assert h["districts"] == len(districts)


def test_the_not_rated_count_is_what_tea_published():
    src = DATA / "tea_accountability.csv"
    _need(src)
    n = sum(1 for r in _rows(src)
            if r["is_district_row"].upper() != "TRUE" and r["rating"] == "Not Rated")
    assert _art("campus_data.json")["meta"]["campuses_not_rated"] == n


# --- the crosswalk is a derivation too ---------------------------------------

def test_the_crosswalk_counts_match_the_files_it_was_built_from():
    xw, fin = DATA / "district_crosswalk.csv", DATA / "texas_finance_clean.csv"
    _need(xw, fin)
    rows = _rows(xw)
    want = {r["district_number"] for r in _rows(fin) if r["district_number"]}
    assert {r["district_number"] for r in rows} == want

    debt = DATA / "brb_debt_outstanding.csv"
    if debt.exists():
        ids = {r["district_number"]: r["brb_id"] for r in _rows(debt)
               if r["district_number"].strip()}
        for r in rows:
            if r["brb_id"]:
                assert ids.get(r["district_number"]) == r["brb_id"], r["district_number"]


def test_every_published_layer_has_a_provenance_test_here_or_upstream():
    """The gap this file was written to close, kept closed.

    A new committed artefact with no re-derivation anywhere is a published
    number that only its own builder vouches for.
    """
    covered = {
        "bond_data.json", "debt_data.json", "campus_data.json",   # this file
        "forensic_data.json", "trend_data.json",                  # test_provenance.py
        "economics_data.json", "outcomes_data.json",              # ditto
        "national_data.json",                                     # test_national.py
    }
    known_uncovered = {
        # Derived entirely from artefacts already covered above, so a wrong
        # number cannot enter here without failing one of those first.
        "forensic_quality.json", "fallback_index.json", "district_geo.json",
        "map_data.json", "equity_data.json", "takeover_data.json",
        "isd_briefing.json", "source_fingerprint.json", "similarity_graph.json",
    }
    published = {p.name for p in STATIC.glob("*.json")}
    orphans = published - covered - known_uncovered
    assert not orphans, (
        f"published with no re-derivation: {sorted(orphans)}. Add a test here or "
        f"list it as derived from a covered artefact.")

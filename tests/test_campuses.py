"""Tests for the campus layer.

This is the most defamation-adjacent data on the site. It attaches a letter
grade to named schools that real children attend, and the temptation it creates
is a statewide campus league table — which would rank a campus serving newly
arrived students against one in a wealthy suburb and call the difference
quality. The layer deliberately does not do that, and several tests here exist
only to keep it that way.

Three refusals are load-bearing:

- "Not Rated" is missing data, not failure. 525 campuses carry it. Counting
  them would manufacture 525 failing schools out of an absence.
- Alternative Education Accountability campuses are rated on a different scale
  and are excluded from the headline, with the including-them figure published
  beside it so the choice is visible rather than trusted.
- The claim is about the gap INSIDE a district, never a comparison across
  districts.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.api import app  # noqa: E402

DATA = ROOT / "static" / "campus_data.json"
pytestmark = pytest.mark.skipif(
    not DATA.exists(),
    reason="run scripts/ingest_tea_accountability.py then build_campus_data.py")

GRADE = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


@pytest.fixture(scope="module")
def d():
    return json.loads(DATA.read_text())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- the headline is what it says it is -------------------------------------

def test_the_headline_is_the_sum_of_its_own_campuses(d):
    """Re-derive it from the per-district records rather than trusting the
    statewide block that was computed alongside them."""
    h = d["texas"]["hidden_by_the_district_average"]
    students = campuses = 0
    districts = set()
    for num, rec in d["districts"].items():
        if GRADE.get(rec["district_rating"], -1) < 3:
            continue
        bad = [c for c in rec["campuses"]
               if GRADE.get(c["rating"], 9) <= 1 and not c["is_alternative_education"]]
        if bad:
            districts.add(num)
            campuses += len(bad)
            students += sum(c["students"] for c in bad)
    assert h["campuses"] == campuses
    assert h["students"] == students
    assert h["districts"] == len(districts)


def test_not_rated_is_never_counted_as_failure(d):
    """525 campuses. Counting them would invent 525 failing schools."""
    assert d["meta"]["campuses_not_rated"] > 400
    for rec in d["districts"].values():
        for c in rec["campuses"]:
            assert c["rating"] in GRADE, f"{c['campus_name']} is {c['rating']!r}"


def test_alternative_education_is_excluded_and_the_choice_is_shown(d):
    """Excluding them is a judgement call, so the other number ships too."""
    h = d["texas"]["hidden_by_the_district_average"]
    inc = h["including_alternative_education"]
    assert inc["campuses"] >= h["campuses"]
    assert inc["students"] >= h["students"]
    for rec in d["districts"].values():
        for c in rec["campuses"]:
            assert isinstance(c["is_alternative_education"], bool)


def test_the_rated_f_subset_is_inside_the_headline(d):
    h = d["texas"]["hidden_by_the_district_average"]
    assert h["rated_f"]["campuses"] <= h["campuses"]
    assert h["rated_f"]["students"] <= h["students"]


# --- best and worst must not be read off a sorted list ----------------------

def test_best_and_worst_are_the_right_way_round(d):
    """The campus list is sorted WORST first and unrated campuses sort past an
    A, so taking the first and last elements reads the list backwards and can
    report 'Not Rated' as a district's best campus. This shipped once."""
    for num, rec in d["districts"].items():
        grades = [GRADE[c["rating"]] for c in rec["campuses"] if c["rating"] in GRADE]
        if not grades:
            continue
        assert GRADE[rec["best"]] == max(grades), num
        assert GRADE[rec["worst"]] == min(grades), num
        assert GRADE[rec["best"]] >= GRADE[rec["worst"]], num
        assert rec["spans_grades"] == max(grades) - min(grades), num


def test_a_single_campus_district_spans_nothing(d):
    for num, rec in d["districts"].items():
        if len(rec["campuses"]) == 1:
            assert rec["spans_grades"] == 0, num
            assert rec["best"] == rec["worst"], num


# --- restraint --------------------------------------------------------------

def test_no_campus_is_ranked_against_another_district(d):
    """A statewide campus league table is a different and far more dangerous
    artefact than the gap inside a district. Only DISTRICTS are listed
    statewide; individual campuses appear solely within their own district."""
    statewide = json.dumps(d["texas"])
    for rec in d["districts"].values():
        for c in rec["campuses"]:
            assert c["campus_number"] not in statewide, (
                f"{c['campus_name']} is named in a statewide list")


def test_nothing_here_alleges_wrongdoing(d):
    blob = json.dumps(d).lower()
    for w in ("failing school", "bad school", "worst school", "fraud",
              "incompeten", "negligen"):
        assert w not in blob, f"the campus layer says '{w}'"
    note = d["meta"]["what_this_is_not"].lower()
    assert note.startswith("none of") and "arithmetic" in note


def test_the_limits_say_a_rating_is_not_a_school(d):
    limits = " ".join(d["meta"]["limits"]).lower()
    assert "not rated" in limits and "excluded" in limits
    assert "alternative education" in limits
    assert "one year" in limits, "a single year must not read as a trend"
    assert "not of a school" in limits


def test_no_individual_is_named(d):
    blob = json.dumps(d).lower()
    for w in ("principal", "superintendent", "teacher of", "board member"):
        assert w not in blob


# --- the endpoints ----------------------------------------------------------

def test_the_statewide_endpoint_serves_the_layer(client):
    body = client.get("/campuses/texas").json()
    assert {"meta", "rating_counts", "hidden_by_the_district_average",
            "spread"} <= set(body)
    assert body["meta"]["limits"]


def test_a_district_endpoint_lists_its_campuses_worst_first(client):
    body = client.get("/district/101912/campuses").json()      # Houston ISD
    assert body["district_number"] == "101912"
    grades = [GRADE[c["rating"]] for c in body["campuses"]]
    assert grades == sorted(grades), "campuses must be worst first"


def test_a_district_with_no_rated_campus_gets_an_absence(client):
    body = client.get("/district/999999/campuses").json()
    a = body["absence"]
    assert a["kind"] == "not_measured"
    assert a["is_finding"] is False, "unrated is not a finding about the schools"
    assert "not a verdict" in a["sentence"].lower()


def test_the_endpoints_need_no_database(client):
    import src.api as api
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), None
    try:
        assert client.get("/campuses/texas").status_code == 200
        assert client.get("/district/101912/campuses").status_code == 200
    finally:
        api.app.state.db_pool = saved

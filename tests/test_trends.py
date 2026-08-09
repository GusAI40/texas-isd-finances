"""Tests for the seventeen-year trend layer.

A trend is a stronger claim than a snapshot: it says something changed, and a
reader will act on the direction. The risks are correspondingly different from
the rest of the site.

  1. **A headline that no longer matches its own series.** The findings are
     prose generated from the data; if the two ever drift, the page states a
     number the chart contradicts. Every headline is re-derived here from the
     series it came from.
  2. **A trend that is really a change in who reports.** Districts open and
     close. The balanced-panel check must exist and must agree.
  3. **The operating-balance definition.** Operating revenue must be compared
     with operating spending only. Including debt service, or the debt tax
     levy that funds it, turns a routine construction year into a crisis — and
     the two are nearly equal statewide, so the error is large.
  4. **NaN in JSON.** json.dumps writes bare NaN, which no strict parser
     accepts; a missing year has to be null.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.api import app  # noqa: E402

DATA = ROOT / "static" / "trend_data.json"
pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="run scripts/build_trend_data.py first")


@pytest.fixture(scope="module")
def payload():
    # strict=True is the point: it rejects NaN and Infinity.
    return json.loads(DATA.read_text(), parse_constant=_reject)


def _reject(name):
    raise AssertionError(f"the payload contains {name}, which is not valid JSON")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- endpoints --------------------------------------------------------------

def test_statewide_serves_without_the_per_district_bulk(client):
    res = client.get("/trends/texas")
    assert res.status_code == 200
    body = res.json()
    assert {"meta", "statewide", "findings", "summary"} <= set(body)
    assert "districts" not in body


def test_a_district_carries_series_change_and_a_state_comparison(client):
    d = client.get("/district/057905/trends").json()
    assert len(d["years"]) >= 15
    for key in ("instruction_share", "instruction_ps", "debt_ps",
                "security_ps", "operating_balance_ps", "federal_ps"):
        assert key in d["series"], key
        assert len(d["series"][key]) == len(d["years"]), key
        assert key in d["change"] and key in d["vs_state"], key
    assert d["statewide"]["years"] == d["meta"]["last_year"] - d["meta"]["first_year"] + 1 \
        or len(d["statewide"]["years"]) >= 15


def test_a_district_with_too_few_years_is_404_not_a_flat_line(client):
    assert client.get("/district/999999/trends").status_code == 404


def test_the_series_covers_seventeen_fiscal_years(payload):
    m = payload["meta"]
    assert m["first_year"] == 2009 and m["last_year"] == 2025
    assert m["years"] == 17
    assert len(payload["statewide"]["years"]) == 17


# --- the findings must match the data they describe -------------------------

def _finding(payload, key):
    return next(f for f in payload["findings"] if f["key"] == key)


def test_every_finding_states_a_number(payload):
    assert len(payload["findings"]) >= 5
    for f in payload["findings"]:
        assert f["headline"] and f["figure"] and f["detail"]
        assert any(c.isdigit() for c in f["figure"]), f["key"]


def test_the_classroom_share_headline_matches_the_series(payload):
    ch = payload["statewide"]["change"]["instruction_share"]
    s = payload["statewide"]["series"]["instruction_share"]
    assert ch["first"] == s[0] and ch["last"] == s[-1]
    assert round(ch["last"] - ch["first"], 1) == ch["change"]
    assert str(ch["first"]) in _finding(payload, "classroom_share")["figure"]
    assert str(ch["last"]) in _finding(payload, "classroom_share")["figure"]


def test_the_classroom_share_actually_fell(payload):
    """If this ever reverses, the page must not keep saying it fell."""
    ch = payload["statewide"]["change"]["instruction_share"]
    assert ch["change"] < 0
    assert "fallen" in _finding(payload, "classroom_share")["headline"].lower()


def test_the_federal_figure_uses_the_real_peak_year(payload):
    s = payload["statewide"]
    peak = max(zip(s["years"], s["series"]["federal_ps"]), key=lambda p: p[1] or 0)
    assert str(peak[0]) in _finding(payload, "federal_cliff")["figure"]


def test_debt_and_security_rose_as_the_headlines_claim(payload):
    for key, finding in (("debt_ps", "debt"), ("security_ps", "security")):
        ch = payload["statewide"]["change"][key]
        assert ch["change"] > 0, key
        assert ch["last"] > ch["first"], key
        assert _finding(payload, finding)


# --- the balanced-panel check ----------------------------------------------

def test_the_trend_is_not_a_change_in_who_reports(payload):
    p = payload["meta"]["balanced_panel_check"]
    assert p["districts"] > 1000
    # Same measure, fixed roster: it may differ a little, not a lot.
    assert abs(p["instruction_share_all"] - p["instruction_share_panel"]) <= 0.5
    assert abs(p["instruction_ps_all"] - p["instruction_ps_panel"]) <= 100


def test_the_panel_check_is_quoted_in_the_headline(payload):
    detail = _finding(payload, "classroom_share")["detail"]
    assert str(payload["meta"]["balanced_panel_check"]["districts"]) in detail.replace(",", "")\
        or f"{payload['meta']['balanced_panel_check']['districts']:,}" in detail


# --- the operating-balance definition --------------------------------------

def test_operating_balance_excludes_debt_on_both_sides(payload):
    """The debt tax levy and debt service are nearly equal statewide, so
    including one without the other moves this by billions. The limits must
    say which side of the line the measure sits on."""
    limits = " ".join(payload["meta"]["limits"]).lower()
    assert "operating revenue" in limits and "operating spending" in limits
    assert "bond proceeds" in limits or "capital" in limits


def test_the_deficit_series_is_internally_consistent(payload):
    for r in payload["statewide"]["deficit_by_year"]:
        assert 0 <= r["in_deficit"] <= r["districts"]
        assert abs(r["in_deficit"] / r["districts"] * 100 - r["pct"]) < 0.15
        assert 0 <= r["students_pct"] <= 100


def test_the_deficit_headline_matches_the_series(payload):
    d = payload["statewide"]["deficit_by_year"]
    f = _finding(payload, "deficits")
    now = d[-1]
    assert str(now["year"]) in f["figure"]
    assert f"{now['pct']}%" in f["detail"]
    # The claim of a first must be a real first.
    if "first time" in f["headline"].lower():
        assert now["statewide_margin"] < 0
        assert all(r["statewide_margin"] > 0 for r in d[:-1]), \
            "headline claims a first, but an earlier year was also negative"


# --- honesty about what a trend is -----------------------------------------

def test_the_limits_refuse_to_claim_a_cause(payload):
    limits = " ".join(payload["meta"]["limits"]).lower()
    assert "not a cause" in limits or "direction, not a cause" in limits
    assert "reclassification" in limits


def test_no_finding_alleges_wrongdoing(payload):
    banned = ("fraud", "corrupt", "illegal", "waste", "abuse", "misuse", "criminal")
    for f in payload["findings"]:
        text = (f["headline"] + " " + f["detail"]).lower()
        for w in banned:
            assert w not in text, f"{f['key']} says '{w}'"


def test_small_districts_are_flagged_and_kept_out_of_rankings(payload):
    cut = payload["meta"]["min_students_for_rankings"]
    small = [d for d in payload["districts"].values() if d["small_district"]]
    assert small, "no small districts flagged — the guard is not working"
    for d in small:
        assert d["note"] and str(cut) in d["note"]
    ranked = {r["n"] for r in payload["summary"]}
    assert not ranked & {d["district_number"] for d in small}


def test_missing_years_are_null_not_nan(payload):
    """json.dumps writes bare NaN, which strict parsers reject. Loading the
    file with parse_constant already proves this, but assert the intent."""
    for num, d in list(payload["districts"].items())[:200]:
        for key, series in d["series"].items():
            for v in series:
                assert v is None or isinstance(v, (int, float)), f"{num}.{key}"


def test_vs_state_marks_the_worrying_direction_per_measure(payload):
    """A rise in debt and a fall in instruction are both bad news. The flag has
    to know which way is which for each measure, or it inverts on half of them."""
    M = payload["meta"]["measures"]
    checked = 0
    for d in payload["districts"].values():
        for key, vs in d["vs_state"].items():
            gap = vs["gap_vs_state"]
            if abs(gap) < 0.001:
                continue
            expect = (gap < 0) if M[key]["fall_is_worrying"] else (gap > 0)
            assert vs["steeper_than_state"] is expect, f"{key} gap={gap}"
            checked += 1
    assert checked > 1000

"""Tests for the forensic file — the layer that composes four money questions.

The risks here are not crashes. They are:

  1. **Overclaiming.** A flag that reads as an accusation, a combined score
     that invents a league table, or a causal claim about one district. The
     payload is asserted against those directly.
  2. **Subtracting instead of composing.** Debt service sits OUTSIDE TEA's
     operating total. If any code ever treats operating as if it included
     debt, every comparison on the page silently understates the districts
     that borrowed most.
  3. **Reporting local revenue net of recapture**, which is how TEA publishes
     it and which makes property-funded districts look state-funded.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.api import app  # noqa: E402

DATA = ROOT / "static" / "forensic_data.json"
pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="run scripts/build_forensic_data.py first")


@pytest.fixture(scope="module")
def payload():
    return json.loads(DATA.read_text())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- the endpoints ----------------------------------------------------------

def test_statewide_serves_without_a_database(client):
    res = client.get("/forensics/texas")
    assert res.status_code == 200
    body = res.json()
    assert {"meta", "statewide", "leaderboards", "table"} <= set(body)
    # The per-district files are the other endpoint; shipping them here would
    # send two megabytes to every reader.
    assert "districts" not in body


def test_a_district_file_answers_all_four_questions(client):
    res = client.get("/district/057905/forensics")
    assert res.status_code == 200
    d = res.json()
    for key in ("outside_operating", "who_pays", "ballot", "where_it_landed"):
        assert d[key], f"{key} is missing for Dallas ISD"
    assert d["district_name"]
    assert d["meta"]["thresholds"]


def test_an_unknown_district_is_404_not_an_empty_file(client):
    assert client.get("/district/999999/forensics").status_code == 404


def test_the_page_serves_and_is_in_the_sitemap(client):
    assert client.get("/forensics").status_code == 200
    assert "/forensics" in client.get("/sitemap.xml").text


def test_the_page_is_counted_as_a_page(client):
    """Analytics counts an allowlist. A page missing from it is invisible."""
    from src import analytics
    assert analytics.countable_path("/forensics") == "/forensics"


# --- composed, never subtracted --------------------------------------------

def test_debt_is_added_to_the_operating_total_not_taken_out_of_it(payload):
    """TEA's operating figure excludes debt service. total = operating + debt.

    If this ever inverts, every district that borrowed heavily is reported as
    spending less on children than it does.
    """
    checked = 0
    for num, d in payload["districts"].items():
        o = d.get("outside_operating")
        if not o or o.get("operating_per_student") is None:
            continue
        assert o["total_per_student"] >= o["operating_per_student"], num
        assert abs(o["total_per_student"]
                   - (o["operating_per_student"] + o["per_student"])) <= 1, num
        checked += 1
    assert checked > 500, "not enough districts carried a debt composition to test"


def test_local_revenue_is_gross_not_net_of_recapture(payload):
    """A district that pays recapture must still be reported on what it
    collected. The basis travels with the number so a reader can check."""
    payers = [d for d in payload["districts"].values()
              if (d.get("who_pays") or {}).get("recapture_per_student")]
    assert payers, "no recapture payers in the dataset"
    for d in payers:
        assert "gross" in (d["who_pays"]["basis"] or "").lower(), d["district_number"]


def test_the_revenue_shares_are_a_whole_dollar(payload):
    for num, d in payload["districts"].items():
        p = d.get("who_pays")
        if not p or p["state_pct"] is None:
            continue
        total = p["local_pct"] + p["state_pct"] + p["federal_pct"]
        assert 98 <= total <= 102, f"{num} revenue shares sum to {total}"


# --- not overclaiming -------------------------------------------------------

def test_there_is_no_combined_score(payload):
    """Adding four unrelated measures would manufacture a league table."""
    banned = {"score", "composite", "index", "grade", "rating", "risk"}
    for num, d in payload["districts"].items():
        assert not (banned & set(d)), f"{num} carries a composite field"
    assert not (banned & set(payload["statewide"]))


def test_every_flag_carries_its_own_number(payload):
    """A flag without a figure is an assertion. With one it is a reading."""
    seen = 0
    for num, d in payload["districts"].items():
        for f in d["flags"]:
            assert f["tone"] in {"watch", "info", "good"}, num
            assert f["label"] and f["detail"], num
            assert any(ch.isdigit() for ch in f["detail"]), \
                f"{num}: flag {f['key']} states no number"
            seen += 1
    assert seen > 100


def test_no_flag_alleges_wrongdoing(payload):
    """This is an account of public money, not an accusation about anyone."""
    banned = ("fraud", "corrupt", "illegal", "waste", "abuse", "misuse",
              "scandal", "steal", "cover-up", "criminal")
    for num, d in payload["districts"].items():
        for f in d["flags"]:
            text = (f["label"] + " " + f["detail"]).lower()
            for w in banned:
                assert w not in text, f"{num}: flag {f['key']} says '{w}'"


def test_no_person_is_named(payload):
    """The bond source has companion files carrying a vendor's CRM — named
    reps, revenue, commissions. None of that may ever reach a payload."""
    blob = json.dumps(payload).lower()
    for w in ("superintendent", "trustee", "board member", "sales rep",
              "commission", "salesperson"):
        assert w not in blob, f"the payload names {w}"


def test_the_thresholds_behind_every_flag_are_published(payload):
    t = payload["meta"]["thresholds"]
    assert {"top_decile", "debt_cents_per_dollar_taught", "local_share_high_pct",
            "athletics_share_pct", "beats_prediction_points",
            "min_propositions_for_a_pass_rate"} <= set(t)


def test_the_limits_say_what_this_cannot_show(payload):
    limits = " ".join(payload["meta"]["limits"]).lower()
    assert "wrongdoing" in limits
    assert "combined score" in limits or "no combined" in limits
    assert "gross" in limits and "recapture" in limits


def test_athletics_is_always_labelled_an_upper_bound(payload):
    """Propositions bundle purposes, so athletics dollars are a ceiling.
    Quoting them as a total would be a lie of selection."""
    for num, d in payload["districts"].items():
        for f in d["flags"]:
            if f["key"] == "athletics":
                assert "upper bound" in f["detail"].lower(), num


# --- percentiles and rankings ----------------------------------------------

def test_percentiles_are_in_range_and_mean_the_same_thing_everywhere(payload):
    for num, d in payload["districts"].items():
        o, p = d.get("outside_operating"), d.get("who_pays")
        for pct in ((o or {}).get("percentile"), (p or {}).get("local_percentile")):
            if pct is not None:
                assert 0 <= pct <= 100, num


def test_the_highest_debt_district_ranks_at_the_top(payload):
    board = payload["leaderboards"]["debt_per_student"]
    assert board
    assert board == sorted(board, key=lambda r: -r["debt"])
    top = payload["districts"][board[0]["n"]]
    assert top["outside_operating"]["percentile"] >= 99


def test_a_flagged_debt_district_really_is_in_the_top_decile(payload):
    cut = payload["meta"]["thresholds"]["top_decile"]
    for num, d in payload["districts"].items():
        if any(f["key"] == "debt_heavy" for f in d["flags"]):
            assert d["outside_operating"]["percentile"] >= cut, num


def test_the_bond_result_is_carried_with_its_fragility(payload):
    """It sat at p=0.061 until the district match was corrected. A borderline
    result must not be published as a settled one."""
    w = payload["statewide"]["did_it_work"]
    if not w:
        pytest.skip("bond outcome test not available")
    assert "p_value" in w and "ci_low" in w and "ci_high" in w
    if 0.01 < w["p_value"] < 0.05:
        assert w["fragile"] is True
    # The interval must actually contain the point estimate.
    assert w["ci_low"] <= w["difference"] <= w["ci_high"]

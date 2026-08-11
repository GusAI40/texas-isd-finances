"""Tests for the forensic-accounting layer.

This layer is the most dangerous thing in the repo, because a forensic test
that looks rigorous and does not fit produces confident false accusations at
scale. The naive per-district Benford run labelled 1,104 of 1,211 Texas
districts "nonconforming"; publishing that would have been a libel generator
with a citation.

So the tests here are mostly about restraint:

- the refusal to publish per-district Benford must ship WITH its evidence, so
  a future maintainer cannot re-enable it without meeting the same bar;
- no test may be reported as evidence of wrongdoing;
- a charter must never appear in the debt-without-a-ballot list, because it
  cannot hold a bond election and so the question does not arise;
- every finding must carry the limits that would let a reader dismiss it.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.api import app  # noqa: E402

DATA = ROOT / "static" / "forensic_quality.json"
pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="run scripts/build_forensic_quality.py first")


@pytest.fixture(scope="module")
def q():
    return json.loads(DATA.read_text())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- restraint --------------------------------------------------------------

def test_nothing_here_alleges_wrongdoing(q):
    banned = ("fraud", "fraudulent", "corrupt", "illegal", "criminal",
              "embezzl", "misappropriat", "cover-up", "laundering")
    blob = json.dumps(q).lower()
    for w in banned:
        assert w not in blob, f"the forensic layer says '{w}'"


def test_the_layer_states_plainly_what_it_is_not(q):
    note = q["meta"]["what_this_is_not"].lower()
    assert "is evidence of wrongdoing" in note and note.startswith("none of")
    assert "coding error" in note
    assert q["meta"]["no_named_individuals"] is True


def test_no_individual_is_named(q):
    blob = json.dumps(q).lower()
    for w in ("superintendent", "trustee", "board member", "cfo", "auditor"):
        assert w not in blob, f"the forensic layer names {w}"


# --- Benford: valid where it is valid, refused where it is not --------------

def test_statewide_benford_is_reported_with_its_statistic(q):
    b = q["benford"]
    assert b["figures_tested"] > 1_000_000
    assert 0 <= b["mad"] < 0.05
    assert b["nigrini_band"] in {"close conformity", "acceptable",
                                 "marginally acceptable", "nonconformity"}
    assert len(b["expected_pct"]) == len(b["observed_pct"]) == 9
    assert abs(sum(b["observed_pct"]) - 100) < 0.5


def test_the_per_district_benford_refusal_ships_with_its_evidence(q):
    """A maintainer must be able to see WHY it is refused, or they will
    re-enable it. The null simulation is that evidence."""
    r = q["benford_per_district_refused"]
    assert r["verdict"] == "per-district Benford is not published"
    assert r["draws_per_size"] >= 100
    assert len(r["null"]) >= 4
    small = min(r["null"], key=lambda x: x["sample_size"])
    large = max(r["null"], key=lambda x: x["sample_size"])
    # The point of the whole thing: perfect data fails at small n and passes
    # at large n, so the band measures sample size rather than conformity.
    assert small["median_mad"] > large["median_mad"] * 3
    assert small["band_it_would_be_assigned"] != "close"
    assert large["band_it_would_be_assigned"] == "close"


def test_no_per_district_benford_score_is_published(q):
    """The scores exist in the analysis and must not reach the payload."""
    blob = json.dumps(q)
    assert '"per_district_mad"' not in blob
    assert '"benford_by_district"' not in blob


# --- reconciliation ---------------------------------------------------------

def test_the_three_identities_are_reported(q):
    ids = q["reconciliation"]["identities"]
    assert len(ids) == 3
    for i in ids:
        assert 0 <= i["reconciles_within_0_1pct"] <= 100
        assert i["district_years"] > 15000
        assert i["gaps_over_1pct"] >= 0


def test_reconciliation_gaps_are_named_and_quantified(q):
    """A gap without the district, the year and the dollar amount is a rumour."""
    rc = q["reconciliation"]
    for g in rc["gaps"]:
        assert g["district_number"] and g["district_name"]
        assert 2009 <= g["year"] <= 2025
        assert g["operating_reported"] > 0
        assert g["unassigned"] != 0
        assert 0 < g["functions_sum_to_pct_of_total"] < 200


def test_the_reconciliation_summary_matches_its_own_gaps(q):
    rc = q["reconciliation"]
    s = rc["summary"]
    assert s["district_years_with_a_gap"] == len(rc["gaps"])
    assert s["distinct_districts"] == len({g["district_number"] for g in rc["gaps"]})
    assert set(s["years_affected"]) == {g["year"] for g in rc["gaps"]}
    assert s["unassigned_total"] == round(sum(g["unassigned"] for g in rc["gaps"]))


def test_reconciliation_is_the_exception_not_the_rule(q):
    """If this ever inverts, the identity is wrong rather than the filings."""
    for i in q["reconciliation"]["identities"]:
        assert i["reconciles_within_0_1pct"] > 95, i["identity"]


# --- debt without a ballot --------------------------------------------------

def test_charters_are_excluded_from_the_debt_question(q):
    """A charter cannot hold a bond election, so 'no voter-approved bond' is
    not a question about it. Including them would repeat the exact error the
    absence layer was built to prevent."""
    for r in q["debt_without_a_ballot"]["no_voter_approved_bond_on_record"]["largest"]:
        assert r["is_charter"] is False, r["district_name"]
        assert r["district_number"][3] != "8", r["district_name"]


def test_every_listed_district_actually_paid_debt_service(q):
    u = q["debt_without_a_ballot"]["no_voter_approved_bond_on_record"]
    for r in u["largest"]:
        assert r["debt_service_paid"] > 0
        assert r["principal_ever_approved"] == 0
        assert r["students"] > 0


def test_the_debt_finding_carries_the_limits_that_could_dismiss_it(q):
    """An absent election is weaker evidence than a present one, and the
    payload has to say so where anyone quoting it will see it."""
    limits = " ".join(q["debt_without_a_ballot"]["limits"]).lower()
    assert "incomplete" in limits            # the ballot record may be
    assert "1958" in limits                  # records begin then
    assert "refund" in limits                # refunding needs no new vote
    assert "charter" in limits


def test_the_debt_reading_does_not_assert_impropriety(q):
    reading = q["debt_without_a_ballot"]["reading"].lower()
    assert "lawful" in reading
    assert "does not answer" in reading or "question" in reading


# --- the endpoint -----------------------------------------------------------

def test_the_endpoint_serves_the_whole_layer(client):
    res = client.get("/forensics/quality")
    assert res.status_code == 200
    body = res.json()
    assert {"meta", "benford", "benford_per_district_refused",
            "reconciliation", "debt_without_a_ballot"} <= set(body)


def test_the_endpoint_needs_no_database(client):
    import src.api as api
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), None
    try:
        assert client.get("/forensics/quality").status_code == 200
    finally:
        api.app.state.db_pool = saved

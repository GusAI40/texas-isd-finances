"""Tests for explained emptiness.

The failure this guards against is subtle and was live for months: a section
with nothing in it rendered as a blank box, and a reader could not tell which
of three very different things had happened.

    NOT_APPLICABLE  a charter levies no property tax — no bill exists, ever
    DID_NOT_HAPPEN  no bond election since 1958; no peer ever turned around
    NOT_MEASURED    the figure is withheld, or there are too few years

"We don't know" and "it didn't happen" mean opposite things. The tests below
exist to keep them apart, and to keep the did_not_happen cases promoted — they
are findings, and treating them as missing data is what threw them away.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import absences as A  # noqa: E402
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


# --- the three kinds must stay distinct -------------------------------------

def test_the_three_kinds_are_distinct_and_documented():
    assert len({A.NOT_APPLICABLE, A.DID_NOT_HAPPEN, A.NOT_MEASURED}) == 3
    for kind, text in A.KINDS.items():
        assert len(text) > 20, kind
    assert "did not" in A.KINDS[A.DID_NOT_HAPPEN].lower()
    assert "not" in A.KINDS[A.NOT_MEASURED].lower()


def test_only_did_not_happen_is_a_finding():
    """A finding is promoted in the UI and quoted by MCP. 'We don't know' must
    never be promoted, because that is how an absence of data becomes a claim."""
    assert A.no_bond_history("X ISD")["is_finding"] is True
    # A charter CANNOT hold a bond election, so its lack of one is not a
    # choice and must never be promoted as one.
    assert A.no_bond_history("X Academy", is_charter=True)["is_finding"] is False
    assert A.no_peer_turnaround("X ISD", 12)["is_finding"] is True
    assert A.no_better_peer("X ISD")["is_finding"] is True
    assert A.no_tax_figure("X ISD", is_charter=True)["is_finding"] is False
    assert A.no_tax_figure("X ISD", is_charter=False)["is_finding"] is False
    assert A.no_trend("X ISD", 4)["is_finding"] is False
    assert A.no_equity_record("X ISD")["is_finding"] is False


def test_a_charter_and_a_withheld_figure_are_not_the_same_absence():
    """Both render as a missing tax bill. One is 'cannot exist', the other is
    'we could not verify it' — conflating them would sixfold overstate our own
    error rate, which is the note the economics builder already carries."""
    charter = A.no_tax_figure("Some Academy", is_charter=True)
    withheld = A.no_tax_figure("Some ISD", is_charter=False)
    assert charter["kind"] == A.NOT_APPLICABLE
    assert withheld["kind"] == A.NOT_MEASURED
    assert "levies no property tax" in charter["sentence"]
    assert "withheld" in withheld["sentence"]


def test_no_peers_is_not_the_same_as_no_peer_turned_around():
    """Zero peers scanned means we could not look. Peers scanned and none
    turned around means we looked and the answer was no."""
    could_not_look = A.no_peer_turnaround("X ISD", 0)
    looked = A.no_peer_turnaround("X ISD", 14)
    assert could_not_look["kind"] == A.NOT_MEASURED
    assert looked["kind"] == A.DID_NOT_HAPPEN
    assert "14" in looked["sentence"]


# --- every absence must be quotable ----------------------------------------

def test_every_absence_sentence_names_the_district_and_stands_alone():
    """These are read aloud in board meetings and pasted into chats. Each has
    to make sense with no surrounding page."""
    for a in (A.no_bond_history("Katy ISD"), A.no_peer_turnaround("Katy ISD", 9),
              A.no_better_peer("Katy ISD", 31.2), A.no_trend("Katy ISD", 5),
              A.no_tax_figure("Katy ISD", True), A.no_tax_figure("Katy ISD", False),
              A.no_bond_history("Katy ISD", is_charter=True),
              A.no_equity_record("Katy ISD"), A.no_outcome_join("Katy ISD"),
              A.nothing_crosses_a_threshold("Katy ISD", 8)):
        assert "Katy ISD" in a["sentence"], a["section"]
        assert len(a["sentence"]) > 60, a["section"]
        assert a["sentence"].endswith("."), a["section"]
        assert a["section"] and a["kind"] in A.KINDS


def test_the_did_not_happen_sentences_carry_their_number():
    """'None of your peers' is weak. 'None of the 14 districts most like you'
    is a finding."""
    assert "14" in A.no_peer_turnaround("X", 14)["sentence"]
    assert "1958" in A.no_bond_history("X")["sentence"]
    assert "8" in A.nothing_crosses_a_threshold("X", 8)["sentence"]


def test_no_absence_claims_a_clean_bill_of_health():
    """Silence was reading as 'nothing wrong here', which this data cannot
    support — it covers four measures, not a district's whole condition."""
    a = A.nothing_crosses_a_threshold("X ISD", 8)
    assert "not a clean bill of health" in a["sentence"]


# --- the built artifact -----------------------------------------------------

def test_every_district_carries_an_absence_summary(payload):
    for num, d in payload["districts"].items():
        assert "absences" in d and "absence_summary" in d, num
        s = d["absence_summary"]
        assert s["count"] == len(d["absences"])
        assert s["findings"] == sum(1 for a in d["absences"] if a["is_finding"])


def test_absences_are_well_formed_everywhere(payload):
    for num, d in payload["districts"].items():
        for a in d["absences"]:
            assert a["kind"] in A.KINDS, num
            assert a["sentence"] and a["section"], num
            assert isinstance(a["is_finding"], bool)
            assert a["is_finding"] == (a["kind"] == A.DID_NOT_HAPPEN), num


def test_a_district_with_no_bond_history_says_so(payload):
    bond = json.loads((ROOT / "static" / "bond_data.json").read_text())["districts"]
    without = [n for n in payload["districts"] if n not in bond]
    assert without, "no districts lack bond history — check the fixture"
    for num in without[:50]:
        sections = {a["section"] for a in payload["districts"][num]["absences"]}
        assert "bonds" in sections, f"{num} has no bond history and does not say so"


def test_the_statewide_rollup_matches_the_districts(payload):
    roll = payload["statewide"]["absences"]
    counted = sum(1 for d in payload["districts"].values() if d["absences"])
    assert roll["districts_with_an_empty_section"] == counted
    assert roll["students_affected"] == sum(
        d["students"] or 0 for d in payload["districts"].values() if d["absences"])
    for section, n in roll["by_section"].items():
        actual = sum(1 for d in payload["districts"].values()
                     if any(a["section"] == section for a in d["absences"]))
        assert actual == n, section


def test_most_absences_turn_out_to_be_findings(payload):
    """The whole premise: emptiness is usually the more interesting answer. If
    this inverts, the module is mislabelling and should be re-read."""
    kinds = payload["statewide"]["absences"]["by_kind"]
    assert kinds.get(A.DID_NOT_HAPPEN, 0) > kinds.get(A.NOT_MEASURED, 0)


# --- through the API and MCP -----------------------------------------------

def test_the_forensic_endpoint_returns_absences(client):
    d = client.get("/district/043914/forensics").json()
    assert d["absences"], "Wylie ISD has no better-performing peer and should say so"
    assert any(a["is_finding"] for a in d["absences"])


def test_turnarounds_explains_an_empty_list(client):
    """The largest fault line in the product: ~48% of requests, 1.57M students.
    Without a database this 503s, so only the contract is asserted here."""
    res = client.get("/district/057905/turnarounds")
    if res.status_code != 200:
        pytest.skip("turnarounds needs the database")
    body = res.json()
    if not body["turnarounds"]:
        assert body.get("absence"), "an empty turnaround list must explain itself"
        assert body["absence"]["sentence"]


def test_mcp_carries_absences_into_the_chat(client):
    """An assistant reporting 'no bond data' when the truth is 'never asked
    voters since 1958' repeats exactly the failure this fixes."""
    from src import mcp_tools
    out = mcp_tools.call_tool("district_forensics", {"district_number": "043914"})
    text = out["content"][0]["text"]
    assert "did NOT happen" in text
    assert out["structuredContent"]["absences"]

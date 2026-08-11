"""Tests for the source-of-truth register.

A register that drifts is worse than none, because it looks like an answer. The
risks here are specific:

- a measure pointing at a source id that does not exist, so "where did this come
  from" resolves to nothing;
- a measure naming a test that no longer exists, so the re-derivation claim is
  false;
- a source with no download URL, which makes "check it yourself" unactionable;
- the page and the API disagreeing, so a reader and a machine get different
  answers to the same question.

The register is also the place a new published figure has to be added. There is
no test that can prove nothing was forgotten, so the ones here make the register
structurally sound and the omission obvious.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import sources as S  # noqa: E402
from src.api import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- structural soundness ---------------------------------------------------

def test_every_measure_resolves_to_a_real_source():
    """'Where did this come from' must resolve, or the register is decoration."""
    for m in S.MEASURES:
        assert m["source"] in S.SOURCES, f"{m['id']} points at unknown source {m['source']}"


def test_every_source_is_actually_used():
    """An orphan source is a claim we no longer stand behind."""
    used = {m["source"] for m in S.MEASURES}
    orphans = set(S.SOURCES) - used
    assert not orphans, f"sources listed but never used: {orphans}"


def test_every_source_can_be_downloaded_by_a_stranger():
    """'Check it yourself' is unactionable without a link, and every one of
    these is a public record — no login, no records request."""
    for k, v in S.SOURCES.items():
        assert v["url"].startswith("https://"), k
        for field in ("title", "publisher", "covers", "authoritative_for"):
            assert v.get(field), f"{k} is missing {field}"


def test_every_measure_names_its_columns_and_arithmetic():
    for m in S.MEASURES:
        assert m["columns"], f"{m['id']} names no columns"
        assert len(m["method"]) > 40, f"{m['id']} does not explain how it is computed"
        assert m["api"].startswith("/"), m["id"]
        assert m["shown_on"], f"{m['id']} is not shown anywhere — why is it published?"


def test_measure_ids_are_unique():
    ids = [m["id"] for m in S.MEASURES]
    assert len(ids) == len(set(ids))


# --- the re-derivation claim must be true -----------------------------------

def test_every_named_test_file_exists():
    """A measure claiming a test that does not exist is a false claim about
    verification, which is worse than claiming nothing."""
    missing = []
    for m in S.MEASURES:
        path = ROOT / m["test"].split("::")[0]
        if not path.exists():
            missing.append((m["id"], m["test"]))
    assert not missing, f"measures name tests that do not exist: {missing}"


def test_every_named_test_function_exists():
    """Stronger: the named function, not just the file."""
    missing = []
    for m in S.MEASURES:
        part = m["test"].split("::")
        if len(part) < 2:
            continue                       # file-level reference is allowed
        text = (ROOT / part[0]).read_text(encoding="utf-8")
        if f"def {part[1]}(" not in text:
            missing.append((m["id"], m["test"]))
    assert not missing, f"named test functions not found: {missing}"


def test_the_headline_measures_are_covered_by_provenance_tests():
    """The figures most likely to be quoted must be re-derived from SOURCE, not
    merely checked against our own output."""
    for key in ("instruction_share", "debt_per_student", "operating_balance",
                "security_per_student"):
        m = next(x for x in S.MEASURES if x["id"] == key)
        assert "test_provenance" in m["test"], f"{key} has no source re-derivation"


# --- the API ----------------------------------------------------------------

def test_provenance_serves_the_whole_register(client):
    res = client.get("/provenance")
    assert res.status_code == 200
    body = res.json()
    assert set(body["sources"]) == set(S.SOURCES)
    assert len(body["measures"]) == len(S.MEASURES)
    assert body["how_to_verify"] and body["limits"]


def test_provenance_carries_the_source_fingerprint(client):
    """The hash of the file every headline is built from. Without it, 'the
    source has not changed' is an assertion rather than a check."""
    fp = client.get("/provenance").json()["source_fingerprint"]
    fixture = ROOT / "tests" / "fixtures" / "provenance.json"
    if not fixture.exists():
        pytest.skip("provenance fixture not built")
    meta = json.loads(fixture.read_text())["meta"]
    shipped = json.loads((ROOT / "static" / "source_fingerprint.json").read_text())
    assert shipped["source_sha256"] == meta["source_sha256"], (
        "the shipped fingerprint disagrees with the fixture — "
        "re-run scripts/build_provenance_fixture.py")
    assert fp["source_sha256"] == meta["source_sha256"]
    assert len(fp["source_sha256"]) == 64


def test_the_sources_page_serves_and_is_reachable(client):
    assert client.get("/sources").status_code == 200
    assert "/sources" in client.get("/sitemap.xml").text
    from src import analytics
    assert analytics.countable_path("/sources") == "/sources"


def test_the_page_and_the_api_cannot_disagree(client):
    """Both are generated from the same register. If the page were hand-written
    it would drift, and a reader and a machine would get different answers."""
    import html as _html
    page = _html.unescape(client.get("/sources").text)   # labels carry apostrophes
    for k, v in S.SOURCES.items():
        assert v["title"] in page, f"{k} missing from the page"
        assert v["url"] in page, f"{k} download link missing from the page"
    for m in S.MEASURES:
        assert m["label"] in page, f"{m['id']} missing from the page"


def test_the_page_links_to_the_machine_readable_form(client):
    assert "/provenance" in client.get("/sources").text


# --- honesty ----------------------------------------------------------------

def test_the_register_states_what_it_cannot_establish(client):
    """Faithful to the source is not the same as the source being right, and
    the register has to say so where it is read."""
    limits = " ".join(S.LIMITS).lower()
    assert "cannot make the source right" in limits
    assert "estimates" in limits
    assert "named individual" in limits
    assert "corrected over time" in limits
    body = client.get("/provenance").json()
    assert body["limits"] == S.LIMITS


def test_no_source_requires_privileged_access():
    """The whole premise is that anyone can repeat this work."""
    blob = json.dumps(S.SOURCES).lower()
    for word in ("api key", "login", "subscription", "licence fee", "foia"):
        assert word not in blob, f"a source mentions {word}"


def test_the_bond_layer_declares_its_join_risk():
    """It is the only layer joined on a name rather than a TEA number, and that
    is the one place a figure can land on the wrong district."""
    note = S.SOURCES["bond_elections"]["note"].lower()
    assert "name" in note and "county" in note
    assert "crm" in note, "the never-ingest rule on the companion files must be stated"


def test_the_operating_balance_definition_is_documented_where_readers_look():
    """It is the definition that moved the answer by 30 points."""
    m = next(x for x in S.MEASURES if x["id"] == "operating_balance")
    assert "other_revenue" in m["method"] or "debt levy" in m["method"]
    assert "excluded" in m["method"].lower()

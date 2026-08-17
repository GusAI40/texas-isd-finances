"""The E-Rate layer: federal connectivity money, re-derived longhand.

House rule from tests/test_provenance_layers.py — headlines are recounted
from the raw file with the csv module and arithmetic, no builder imported.
The raw USAC CSVs are not committed (they are re-ingested from Socrata), so
those tests skip cleanly where the files are absent and run in any tree
that has done the ingest.

The one rule this layer lives or dies on: **Funded-only**. A Pending FRN's
funding_commitment_request is the amount asked, not granted — the all-status
sum for FY2018 is ~$657M against a real (Funded) $301M, a scandal-shaped
category error that nearly got published during scoping. A test here holds
the artifact to the Funded-only sum AND asserts the all-status sum is
materially different, so the refusal itself is enforced.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA, STATIC = ROOT / "data", ROOT / "static"
FRN_CSV = DATA / "usac_erate_frns.csv"
MATCH_CSV = DATA / "erate_district_match.csv"
INDEX = (STATIC / "index.html").read_text()


def _art() -> dict:
    p = STATIC / "erate_data.json"
    if not p.exists():
        pytest.skip("erate_data.json not built")
    return json.loads(p.read_text())


def _need(*paths: Path):
    for p in paths:
        if not p.exists():
            pytest.skip(f"{p.name} not present (raw USAC files are re-ingested, "
                        f"not committed)")


# ----------------------------------------------------------- the funded rule

def test_the_statewide_series_rederives_funded_only_from_the_raw_file():
    """FY2018 committed/disbursed recounted from the raw rows under the same
    Funded-only rule, and the all-status sum shown to be a DIFFERENT number —
    so the rule is load-bearing, not decorative."""
    _need(FRN_CSV)
    funded_c = funded_d = all_c = 0.0
    for r in csv.DictReader(FRN_CSV.open()):
        if r["funding_year"] != "2018":
            continue
        c = float(r["funding_commitment_request"] or 0)
        all_c += c
        if r["form_471_frn_status_name"] == "Funded":
            funded_c += c
            funded_d += float(r["total_authorized_disbursement"] or 0)
    art = _art()
    y2018 = next(y for y in art["texas"]["years"] if y["year"] == 2018)
    assert y2018["committed"] == round(funded_c)
    assert y2018["disbursed"] == round(funded_d)
    # The trap the rule exists for: requests masquerading as commitments.
    assert all_c > funded_c * 1.5, (
        "the all-status sum no longer dwarfs the Funded sum — if USAC purged "
        "stale Pending rows, revisit whether the funded_only note still "
        "describes a live hazard")


def test_the_buckets_sum_to_the_years_to_the_cent():
    """Every Funded dollar lands in exactly one bucket — attributed,
    unresolved, consortium, or school/library. Dollars must not leak."""
    art = _art()
    years = sum(y["committed"] for y in art["texas"]["years"])
    buckets = sum(b["committed"] for b in art["texas"]["buckets"].values())
    assert abs(years - buckets) <= 2   # rounding of independent sums


def test_district_years_sum_to_district_totals():
    art = _art()
    for tea, rec in list(art["districts"].items())[:200]:
        assert abs(sum(y["committed"] for y in rec["years"]) - rec["committed"]) <= 2, tea
        assert abs(sum(y["disbursed"] for y in rec["years"]) - rec["disbursed"]) <= 2, tea


# ---------------------------------------------------------------- the match

def test_the_match_accounting_balances_and_refusals_are_recorded():
    """matched + refused + unmatched must equal every district-applicant BEN,
    and the Dawson twin-name conflict must be a recorded refusal, not a
    guess — the two Dawson ISDs are a real pair and the entity's own code
    and campuses disagree about which one it is."""
    _need(MATCH_CSV)
    rows = list(csv.DictReader(MATCH_CSV.open()))
    matched = sum(1 for r in rows if r["district_number"])
    conflicts = [r for r in rows if r["method"].startswith("CONFLICT")]
    unmatched = sum(1 for r in rows if r["method"] == "unmatched")
    assert matched + len(conflicts) + unmatched == len(rows)
    m = _art()["meta"]["match"]
    assert m["district_bens"] == len(rows)
    assert m["matched"] == matched
    assert m["conflicts_refused"] == len(conflicts)
    for r in conflicts:
        assert not r["district_number"], "a conflict must never resolve"


def test_no_charter_network_money_lands_on_a_single_district():
    """Harmony, Great Hearts, ResponsiveEd and friends file under ONE
    applicant number for MANY TEA districts. Attributing that money to any
    one of their districts is a wrong-district claim; it must sit in the
    unresolved bucket instead."""
    _need(MATCH_CSV)
    networks = ("Harmony Public Schools", "Great Hearts America-Texas",
                "Responsive Education Solution")
    rows = {r["entity_name"]: r for r in csv.DictReader(MATCH_CSV.open())}
    for name in networks:
        if name in rows:
            assert not rows[name]["district_number"], (
                f"{name} spans several TEA districts and must not be "
                f"attributed to one")


# ---------------------------------------------------------------- the frame

def test_the_limits_name_what_this_money_is_not():
    limits = " ".join(_art()["meta"]["limits"])
    assert "vendors" in limits              # not district spending
    assert "Consortium" in limits           # never split to members
    assert "floor" in limits                # open-year drawn pct
    assert "refused" in limits              # the join refuses, never guesses
    assert "inflation" in limits


def test_recent_years_are_flagged_open_and_closed_years_are_not():
    """The open flag is what stops a 52%-drawn current year reading as
    money left on the table."""
    art = _art()
    years = {y["year"]: y for y in art["texas"]["years"]}
    assert years[2017]["invoicing_open"] is False
    assert years[max(years)]["invoicing_open"] is True


# ------------------------------------------------------------------- the UI

def test_the_erate_card_and_its_explainer_exist():
    assert 'id="econ-erate"' in INDEX
    assert "'erate':" in INDEX, "the ? explainer entry is gone"
    assert "drawn so far" in INDEX
    assert "floor" in INDEX


# ------------------------------------------------------------- the endpoints

def test_endpoints_serve_and_a_missing_district_gets_the_consortium_caveat():
    from fastapi.testclient import TestClient

    from src.api import app
    art = _art()
    with TestClient(app) as c:
        tx = c.get("/erate/texas").json()
        assert "districts" not in tx
        assert tx["texas"]["years"][0]["year"] == art["meta"]["first_year"]
        d = c.get("/district/057905/erate").json()
        assert d["committed"] == art["districts"]["057905"]["committed"]
        missing = next(n for n in ("999999",) if n not in art["districts"])
        a = c.get(f"/district/{missing}/erate").json()
        assert "consortium" in a["absence"]["sentence"]

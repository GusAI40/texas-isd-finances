"""The national layer: Texas against the other 49, re-derived longhand.

Follows the house rule from tests/test_provenance_layers.py — every headline
is recounted from the raw federal file with the csv module (or openpyxl for
the one xlsx, which has no stdlib reader) and plain arithmetic, without
importing the builder. A builder that computes a figure wrongly asserts it
wrongly too; these do not.

The NPEFS state file is small and committed, so the state-rank re-derivation
runs everywhere including CI. The 6 MB Census district file and 8 MB CCD
directory are not committed; their tests skip cleanly when absent and run in
any working tree that has done the ingest.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA, STATIC = ROOT / "data", ROOT / "static"
NPEFS = DATA / "npefs_state_2024.txt"
F33 = DATA / "census_f33_2024.xlsx"
BRIDGE = DATA / "ccd_lea_directory_2425.csv"
INDEX = (STATIC / "index.html").read_text()


def _art() -> dict:
    p = STATIC / "national_data.json"
    if not p.exists():
        pytest.skip("national_data.json not built")
    return json.loads(p.read_text())


def _need(*paths: Path):
    for p in paths:
        if not p.exists():
            pytest.skip(f"{p.name} not present (raw sources are not committed)")


# ------------------------------------------------------- the state ranking

def test_the_state_rank_rederives_from_the_committed_npefs_file():
    """Texas 44th of 51 is recounted from NCES's own file, which is committed,
    so this guarantee holds in CI and not just on the machine that built it."""
    _need(NPEFS)
    with NPEFS.open(newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    states = [r for r in rows if int(r["FIPS"]) <= 56]
    assert len(states) == 51, "the ranking must be 50 states + DC, nothing else"
    ranked = sorted(states, key=lambda r: -int(r["PPE15"]))
    tx = next(r for r in ranked if r["STABR"] == "TX")

    art = _art()["states"]["texas"]
    assert art["rank"] == ranked.index(tx) + 1
    assert art["of"] == 51
    assert art["ppe"] == int(tx["PPE15"])
    # The published figure must BE the division the page says it is.
    assert abs(int(tx["NCE13"]) / int(tx["ADA"]) - art["ppe"]) < 1.0
    assert art["numerator_current_expenditure"] == int(tx["NCE13"])
    assert art["denominator_ada"] == int(tx["ADA"])


def test_territories_are_excluded_and_the_artifact_says_who_is_ranked():
    art = _art()["states"]
    assert len(art["rows"]) == 51
    abbrs = {r["abbr"] for r in art["rows"]}
    for territory in ("PR", "GU", "VI", "AS", "MP"):
        assert territory not in abbrs, f"{territory} must not be in the ranking"
    assert "District of Columbia" in art["texas"]["who"]


# --------------------------------------------------- the district percentile

def test_the_district_percentile_rederives_from_the_census_file():
    """Dallas ISD's percentile, recounted from the Census file without the
    builder: same pool rule, same strictly-less definition."""
    _need(F33)
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(F33, read_only=True)
    ws = wb["elsec24t"]
    rows = ws.iter_rows(values_only=True)
    hdr = [str(c) for c in next(rows)]
    i = {c: n for n, c in enumerate(hdr)}
    pool, dallas = [], None
    for r in rows:
        e, pp = r[i["ENROLL"]], r[i["PPCSTOT"]]
        if (isinstance(e, (int, float)) and isinstance(pp, (int, float))
                and e >= 500 and pp > 0):
            pool.append(pp)
        if str(r[i["NCESID"]]) == "4816230":
            dallas = pp
    art = _art()
    assert art["national"]["districts_in_pool"] == len(pool)
    below = sum(1 for p in pool if p < dallas)
    # floor, not round: "more per student than X%" must be TRUE, and floor is
    # the largest X for which it is (round overstates half the time and can
    # reach the logically-false 100 at the top of the pool).
    assert art["districts"]["057905"]["pctile"] == int(100 * below / len(pool))
    assert art["districts"]["057905"]["ppcs"] == int(dallas)
    pool.sort()
    mid = len(pool) // 2
    median = pool[mid] if len(pool) % 2 else (pool[mid - 1] + pool[mid]) / 2
    assert art["national"]["median_ppcs"] == int(median)


def test_the_bridge_is_keyed_by_number_not_name():
    """The map once drew five districts on the wrong land because a name-keyed
    join guessed between the eleven twin names. This join must go through
    ST_LEAID, and the one row a reader can check against both agencies is
    checked here against the raw directory file."""
    _need(BRIDGE)
    dallas = None
    with BRIDGE.open(encoding="latin-1", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["FIPST"] == "48" and row["ST_LEAID"] == "TX-057905":
                dallas = row["LEAID"]
                break
    assert dallas == "4816230"
    assert _art()["districts"]["057905"]["leaid"] == dallas


# ------------------------------------------------------------- the accounting

def test_the_coverage_accounting_balances():
    """Rows in must equal rows resolved plus rows named as unresolved, and
    every district absent from the layer must have a recorded REASON — a
    closed charter answered 'missing information' instead of 'cannot exist'
    is the wrong-reason failure the absences module exists to prevent."""
    art = _art()
    c = art["meta"]["coverage"]
    assert c["tx_resolved_to_tea"] + len(c["tx_unresolved"]) == c["tx_finance_rows"]
    assert c["tx_resolved_to_tea"] == len(art["districts"])
    assert c["econ_covered"] + c["econ_absent"] == c["econ_districts"]
    # The absence map spans the whole crosswalk (closed charters included),
    # so every econ-layer absence must be a subset of it with a reason.
    econ = set(json.loads(
        (STATIC / "economics_data.json").read_text())["districts"].keys())
    econ_absent = econ - set(art["districts"])
    assert len(econ_absent) == c["econ_absent"]
    assert econ_absent <= set(art["absent"])
    assert c["econ_absent_charters"] == sum(
        1 for d in econ_absent if art["absent"][d] == "charter")
    # No district is both present and absent.
    assert not set(art["absent"]) & set(art["districts"])


def test_the_limits_say_what_this_number_is_not():
    """The four sentences that keep the layer honest, held to the artifact."""
    limits = " ".join(_art()["meta"]["limits"])
    assert "fiscal 2025" in limits          # a year behind TEA, said out loud
    assert "construction" in limits         # current spending is not all-in
    assert "average daily attendance" in limits
    assert "charter" in limits.lower()      # absent by construction, stated
    assert "500" in limits                  # the site-wide ranking rule


def test_the_artifact_quotes_the_census_definition_not_a_paraphrase():
    meta = _art()["meta"]
    assert "students not included in its fall membership counts" in (
        meta["census_per_pupil_definition"]), (
        "the publisher's own definition is the only honest formula statement "
        "for PPCSTOT — it is deliberately NOT TCURSPND/ENROLL")


# ------------------------------------------------------------------- the UI

def test_the_national_card_and_its_explainer_exist():
    assert 'id="econ-national"' in INDEX
    assert "'national':" in INDEX, "the ? explainer entry is gone"
    assert "construction and debt excluded" in INDEX
    assert "500+ students" in INDEX


def test_the_ui_derives_and_never_recomputes():
    """Percentile, rank and pool arrive derived in the payload; the card and
    the did-you-know sentence format them only. ordSuf guards against '44th'
    regressions like the '91th' that shipped once."""
    assert "tx.rank + ordSuf(tx.rank)" in INDEX


# ------------------------------------------------------------- the endpoints

def test_the_statewide_endpoint_serves_meta_and_states_only():
    from fastapi.testclient import TestClient

    from src.api import app
    with TestClient(app) as c:
        body = c.get("/national/texas").json()
        assert "districts" not in body and "absent" not in body
        assert body["states"]["texas"]["of"] == 51
        d = c.get("/district/057905/national").json()
        assert d["ppcs"] == _art()["districts"]["057905"]["ppcs"]
        assert d["meta"]["limits"]


def test_a_charter_gets_a_not_applicable_absence_not_a_blank():
    """Including a CLOSED charter, which lives in the crosswalk but not the
    econ layer — the first cut of the absence map only covered econ
    districts, so closed charters got 'missing information' instead of
    'cannot exist'."""
    from fastapi.testclient import TestClient

    from src.api import app
    art = _art()
    charter = next((k for k, v in art["absent"].items() if v == "charter"), None)
    if charter is None:
        pytest.skip("no charter absences in artifact")
    with TestClient(app) as c:
        body = c.get(f"/district/{charter}/national").json()
        assert body["absence"]["kind"] == "not_applicable"
        assert "government" in body["absence"]["sentence"]
        assert body["district_name"], "the absence response must name the district"
        closed = c.get("/district/014802/national").json()   # closed charter
        assert closed["absence"]["kind"] == "not_applicable"

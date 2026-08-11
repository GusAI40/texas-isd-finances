"""Tests for the district crosswalk.

This file is the answer to "should each district get a UUID?". It is not one.
The TEA number already does the job an identifier has — 103 districts renamed
inside this window and kept their number, and none was ever reused — and it is
the only identifier here a reader can take to the state and check. Minting our
own would add a third thing to keep in sync, would not touch the hard step
(sources send NAMES), and would make us the authority instead of Texas.

What was actually missing was somewhere to write down the reconciliation, which
was being recomputed from scratch on every run and discarded. That is this
table, and these tests exist because a lookup table nobody checks is how a
wrong mapping becomes permanent.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CSV = ROOT / "data" / "district_crosswalk.csv"
pytestmark = pytest.mark.skipif(
    not CSV.exists(), reason="run scripts/build_district_crosswalk.py first")


@pytest.fixture(scope="module")
def rows():
    import csv as _csv
    with CSV.open(encoding="utf-8", newline="") as fh:
        return list(_csv.DictReader(fh))


# --- the key is the state's, and it behaves like a key ----------------------

def test_the_district_number_is_the_key_and_is_unique(rows):
    nums = [r["district_number"] for r in rows]
    assert len(nums) == len(set(nums))
    for n in nums:
        assert len(n) == 6 and n.isdigit(), n


def test_the_county_code_is_the_first_three_digits(rows):
    """This is why the TEA number beats a minted id: it carries its own county,
    which is what resolved the bond join and caught a double-counted district.
    A UUID would have thrown this away."""
    for r in rows:
        if r["county_code"]:
            assert r["district_number"].startswith(r["county_code"]), r["district_number"]


def test_the_fourth_digit_still_identifies_a_charter(rows):
    """Half the absence logic in this project turns on this."""
    for r in rows:
        is_charter = r["is_charter"].lower() == "true"
        assert is_charter == (r["district_number"][3] == "8"), r["district_number"]


# --- the knowledge that used to be thrown away ------------------------------

def test_renamed_districts_keep_their_number_and_their_history(rows):
    """A rename is exactly the case a stable identifier exists to survive.
    Aransas County ISD became Rockport-Fulton ISD and stayed 004901."""
    renamed = [r for r in rows if r["former_names"]]
    assert len(renamed) > 50, "the rename history was dropped"
    aransas = next(r for r in rows if r["district_number"] == "004901")
    assert "ROCKPORT-FULTON" in aransas["district_name"].upper()
    assert "ARANSAS" in aransas["former_names"].upper()


def test_the_disambiguator_suffix_survives_as_an_alias(rows):
    """'Edgewood ISDa' is how the ballot record distinguishes one of the twelve
    shared names. Losing that alias is what silently dropped 147 propositions
    the first time."""
    aliased = [r for r in rows if r["aliases"]]
    assert aliased, "no aliases recorded at all"
    blob = " ".join(r["aliases"] for r in aliased)
    assert "ISDa" in blob or "ISDb" in blob


def test_shared_names_are_separated_by_county_not_by_guesswork(rows):
    """Twelve names belong to more than one district. Every one of those
    districts must carry a county, or nothing downstream can tell them apart."""
    from collections import Counter
    shared = {n for n, c in Counter(r["district_name"] for r in rows).items() if c > 1}
    assert shared, "the shared-name problem cannot have disappeared"
    for r in rows:
        if r["district_name"] in shared:
            assert r["county"], f"{r['district_number']} shares a name and has no county"
    for name in shared:
        counties = [r["county"] for r in rows if r["district_name"] == name]
        assert len(set(counties)) == len(counties), f"{name}: two districts, one county"


# --- the joins it is supposed to serve --------------------------------------

def test_the_bond_review_id_maps_one_to_one(rows):
    """The Board lists three issuers under two names each, including one id
    serving identical data under two contradictory county labels. If an id ever
    maps to two districts here, that double-count is back."""
    seen = {}
    for r in rows:
        if not r["brb_id"]:
            continue
        assert r["brb_id"] not in seen, (
            f"brb_id {r['brb_id']} claimed by {seen.get(r['brb_id'])} "
            f"and {r['district_number']}")
        seen[r["brb_id"]] = r["district_number"]
    assert len(seen) > 900


def test_no_charter_claims_a_census_boundary(rows):
    """A charter has no geographic jurisdiction. A boundary against one would
    mean the TIGER join had attached somebody else's polygon."""
    for r in rows:
        if r["is_charter"].lower() == "true":
            assert r["has_boundary"].lower() == "false", r["district_number"]


def test_every_district_the_finance_data_knows_is_present(rows):
    """The crosswalk is only useful if it is complete. A district missing here
    would resolve to nothing and vanish from a layer without an error."""
    import csv as _csv
    fin = ROOT / "data" / "texas_finance_clean.csv"
    if not fin.exists():
        pytest.skip("source CSV not present")
    with fin.open(encoding="utf-8", newline="") as fh:
        want = {r["district_number"] for r in _csv.DictReader(fh) if r["district_number"]}
    have = {r["district_number"] for r in rows}
    assert not (want - have), f"missing from the crosswalk: {sorted(want - have)[:5]}"


def test_a_missing_county_is_only_ever_a_brand_new_district(rows):
    """Four districts have no county: all are charters that first appear in the
    most recent year and are not yet in TEA's Snapshot file. Any OTHER district
    without a county means the county join has started failing."""
    last = max(int(r["last_year"]) for r in rows)
    for r in rows:
        if not r["county"]:
            assert int(r["first_year"]) == last, (
                f"{r['district_number']} {r['district_name']} has no county and is "
                f"not new (first seen {r['first_year']})")


# --- it must not become a second source of truth ----------------------------

def test_the_crosswalk_invents_no_identifier_of_its_own(rows):
    """The entire argument against a UUID. Every column here is either the
    state's own value or a fact derived from it; nothing is minted by us,
    because a minted id is checkable against nobody but us."""
    banned = ("uuid", "guid", "internal_id", "surrogate", "pk", "row_id")
    header = set(rows[0])
    for col in header:
        assert not any(b in col.lower() for b in banned), f"minted identifier: {col}"

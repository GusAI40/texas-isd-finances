"""Tests for name→district resolution.

Two failures matter here and they are not symmetric. Dropping an election
makes a district page incomplete; attaching one to the WRONG district puts a
false claim in public. The tests below are weighted accordingly: the
mis-attribution cases are exhaustive, the drop cases are representative.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.district_match import Resolver, county_key, stem  # noqa: E402

# The real pairs that collide, with the county that separates them.
TEA = [
    ("043914", "WYLIE ISD"), ("221912", "WYLIE ISD"),
    ("057911", "HIGHLAND PARK ISD"), ("188903", "HIGHLAND PARK ISD"),
    ("015915", "NORTHSIDE ISD"), ("244905", "NORTHSIDE ISD"),
    ("091914", "S AND S CISD"), ("058909", "SANDS CISD"),
    ("072903", "STEPHENVILLE"), ("177901", "ROSCOE ISD"),
    ("214901", "RIO GRANDE CITY CISD"), ("201914", "WEST RUSK ISD"),
    ("118902", "IRION COUNTY ISD"), ("053001", "CROCKETT COUNTY CONSOLIDATED CSD"),
    ("172905", "PEWITT CISD"), ("057905", "DALLAS ISD"),
]
COUNTIES = {"043": "COLLIN", "221": "TAYLOR", "057": "DALLAS", "188": "POTTER",
            "015": "BEXAR", "244": "WILBARGER", "091": "GRAYSON", "058": "DAWSON",
            "072": "ERATH", "177": "NOLAN", "214": "STARR", "201": "RUSK",
            "118": "IRION", "053": "CROCKETT", "172": "MORRIS"}


@pytest.fixture
def r():
    return Resolver.from_tea(TEA, COUNTIES)


# --- stemming ---------------------------------------------------------------

@pytest.mark.parametrize("name,want", [
    ("Pewitt ISD", "PEWITT"), ("PEWITT CISD", "PEWITT"), ("Pewitt", "PEWITT"),
    ("Stephenville ISD", "STEPHENVILLE"), ("STEPHENVILLE", "STEPHENVILLE"),
    ("Knox City-O'Brien ISD", "KNOXCITYOBRIEN"),
    ("Crockett County Cons CSD", "CROCKETTCOUNTY"),
    ("CROCKETT COUNTY CONSOLIDATED CSD", "CROCKETTCOUNTY"),
    ("Irion Co ISD", "IRIONCOUNTY"), ("IRION COUNTY ISD", "IRIONCOUNTY"),
    ("Roscoe Collegiate ISD", "ROSCOE"), ("ROSCOE ISD", "ROSCOE"),
])
def test_stem_ignores_spelling_that_is_not_identity(name, want):
    assert stem(name) == want


def test_the_ab_disambiguator_is_not_part_of_the_name():
    """'Wylie ISDa' is the source telling us there are two. It is not a name."""
    assert stem("Wylie ISDa") == stem("Wylie ISDb") == stem("WYLIE ISD") == "WYLIE"


def test_a_trailing_lowercase_letter_elsewhere_survives():
    """Only the letter glued to the district-type word is a disambiguator."""
    assert stem("Cayuga ISD") == "CAYUGA"
    assert stem("Alba-Golden ISD") == "ALBAGOLDEN"


def test_county_key_ignores_tea_code_and_spacing():
    assert county_key("234 VAN ZANDT") == county_key("Van Zandt") == "VANZANDT"


# --- the mis-attribution cases ----------------------------------------------

@pytest.mark.parametrize("name,county,want", [
    ("Wylie ISDa", "Collin", "043914"), ("Wylie ISDb", "Taylor", "221912"),
    ("Highland Park ISDa", "Dallas", "057911"),
    ("Highland Park ISDb", "Potter", "188903"),
    ("Northside ISDa", "Bexar", "015915"),
    ("Northside ISDb", "Wilbarger", "244905"),
    # The pair that actually WAS mis-attributed: different names, same squash.
    ("S and S CISD", "Grayson", "091914"), ("Sands CISD", "Dawson", "058909"),
])
def test_shared_names_go_to_the_district_the_county_says(r, name, county, want):
    got, method = r.resolve(name, county)
    assert got == want, f"{name} ({county}) resolved to {got}"
    assert method == "name+county"


def test_a_shared_name_without_a_county_is_refused_not_guessed(r):
    """Guessing here is how an election lands on the wrong district."""
    got, method = r.resolve("Wylie ISD", "")
    assert got is None and method == "unmatched"


def test_a_shared_name_with_the_wrong_county_is_refused(r):
    assert r.resolve("Wylie ISD", "Harris")[0] is None


# --- the silent-drop cases --------------------------------------------------

@pytest.mark.parametrize("name,county,want", [
    ("Stephenville ISD", "Erath", "072903"),      # TEA omits the "ISD"
    ("Pewitt ISD", "Morris", "172905"),           # ISD vs CISD
    ("Irion Co ISD", "Irion", "118902"),          # Co vs County
    ("Crockett County Cons CSD", "Crockett", "053001"),
])
def test_spelling_differences_do_not_drop_an_election(r, name, county, want):
    assert r.resolve(name, county)[0] == want


@pytest.mark.parametrize("name,county,want", [
    ("Roscoe Collegiate ISD", "Nolan", "177901"),
    ("Rio Grande City Grulla ISD", "Starr", "214901"),
    ("West Rusk County CISD", "Rusk", "201914"),
])
def test_renamed_districts_keep_their_own_history(r, name, county, want):
    assert r.resolve(name, county)[0] == want


def test_a_rename_match_is_labelled_as_the_weaker_evidence_it_is(r):
    """These are the only matches a human should re-read, so they must be
    findable by method rather than by memory."""
    assert r.resolve("Rio Grande City Grulla ISD", "Starr")[1] == "prefix+county"
    assert r.resolve("Dallas ISD", "Dallas")[1] == "name+county"


def test_prefix_matching_will_not_reach_across_counties(r):
    assert r.resolve("Rio Grande City Grulla ISD", "Dallas")[0] is None


def test_prefix_matching_refuses_short_stems():
    """Two letters in common is not a rename. Requiring length is what keeps
    the loosest rule from becoming a fuzzy match."""
    res = Resolver.from_tea([("001901", "AB ISD"), ("001902", "ABCDEFGH ISD")],
                            {"001": "ANDERSON"})
    assert res.resolve("ABC ISD", "Anderson")[0] is None


def test_an_unknown_district_stays_unknown(r):
    assert r.resolve("Springfield ISD", "Shelbyville")[0] is None
    assert r.resolve("", "Dallas")[0] is None


# --- the built artifact -----------------------------------------------------

def test_published_bond_data_matched_everything_and_says_how():
    """The artifact is what ships, so assert against it, not the builder."""
    import json
    p = Path(__file__).resolve().parent.parent / "static" / "bond_data.json"
    meta = json.loads(p.read_text())["meta"]
    assert meta["matched_pct"] == 100.0
    assert meta["unmatched_issuers"] == []
    assert set(meta["match_methods"]) <= {"name+county", "name", "prefix+county"}
    # The overwhelming majority must be the exact method; if that ever drops,
    # the join has quietly become guesswork.
    total = sum(meta["match_methods"].values())
    assert meta["match_methods"]["name+county"] / total > 0.95


def test_every_district_carries_its_match_provenance():
    import json
    p = Path(__file__).resolve().parent.parent / "static" / "bond_data.json"
    districts = json.loads(p.read_text())["districts"]
    assert districts, "bond data has no districts"
    for num, rec in districts.items():
        assert rec["match"]["method"] in {"name+county", "name", "prefix+county"}, num
        assert rec["match"]["source_names"], num

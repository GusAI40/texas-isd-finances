"""Tests for the one place a published number is turned into text.

Three modules used to do this independently, and the duplication behaved
exactly the way duplicated formatting always does: a bug was fixed in one copy
and the others kept shipping it. Two of the functions even shared a name while
meaning opposite things — `_usd` in src/mcp_tools was exact, `_usd` in
scripts/isd_intel abbreviated, so the same call rendered $1,500,000 as
"$1,500,000" in one output and "$2M" in another.

Each test below is one of the defects that existed in at least one copy at the
moment this module was written.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import format as fmt  # noqa: E402

# --- the sign bug -----------------------------------------------------------

def test_the_sign_goes_before_the_currency_mark():
    """'$-354' is not how anyone writes money. It was fixed in mcp_tools and
    the briefing generator kept producing it for months."""
    assert fmt.usd(-354) == "-$354"
    assert fmt.big(-1_500_000) == "-$1.5M"
    assert not fmt.usd(-354).startswith("$-")


# --- the precision bug ------------------------------------------------------

def test_abbreviating_never_changes_the_number_by_a_third():
    """The replaced implementation rendered $1.5m as '$2M' — in output that
    gets emailed."""
    assert fmt.big(1_500_000) == "$1.5M"
    assert fmt.big(1_499_999) == "$1.5M"
    assert fmt.big(236_668_766_635) == "$236.7B"


def test_nothing_below_a_million_is_abbreviated():
    """'$1K' for $1,234 is not a rounding, it is a different number. Per-student
    figures live in exactly this range."""
    assert fmt.big(1_234) == "$1,234"
    assert fmt.big(23_420) == "$23,420"
    assert fmt.big(999_999) == "$999,999"


def test_exact_stays_exact():
    assert fmt.usd(1_500_000) == "$1,500,000"
    assert fmt.usd(23_420.004) == "$23,420"
    assert fmt.usd(0) == "$0"


def test_missing_is_not_zero():
    """A district with no figure and a district with a figure of nothing are
    different claims."""
    assert fmt.usd(None) == "unknown"
    assert fmt.big(None) == "unknown"
    assert fmt.usd(None, unknown="") == ""
    assert fmt.usd(0) == "$0"


# --- the name bugs ----------------------------------------------------------

def test_a_letter_after_an_apostrophe_is_capitalised():
    """All three copies produced 'D'hanis ISD' because each independently used
    a plain .capitalize()."""
    assert fmt.district_name("D'HANIS ISD") == "D'Hanis ISD"


def test_and_is_lower_case_because_s_and_s_cisd_is_a_real_district():
    """'S And S CISD' is nobody. The district is in Grayson County and it also
    happens to be one of the two names that caused the original bond
    mis-attribution, so it is worth getting right in print as well."""
    assert fmt.district_name("S AND S CISD") == "S and S CISD"


def test_hyphenated_names_capitalise_both_halves():
    assert fmt.district_name("LINDEN-KILDARE CISD") == "Linden-Kildare CISD"


def test_the_district_type_always_shouts():
    for raw, want in (("DALLAS ISD", "Dallas ISD"),
                      ("WEST HARDIN COUNTY CISD", "West Hardin County CISD"),
                      ("SOUTH TEXAS ISD", "South Texas ISD")):
        assert fmt.district_name(raw) == want


def test_a_source_that_already_used_mixed_case_is_trusted():
    """TEA shouts; the Bond Review Board does not. Re-casing a name that was
    already written properly is how 'Rio Grande City Grulla ISD' would become
    'Rio Grande City Grulla Isd'."""
    assert fmt.district_name("Rio Grande City Grulla isd") == "Rio Grande City Grulla ISD"
    assert fmt.district_name("Sanford-Fritch ISD") == "Sanford-Fritch ISD"


def test_an_empty_name_does_not_become_the_word_none():
    assert fmt.district_name(None) == ""
    assert fmt.district_name("", unknown="unknown district") == "unknown district"


# --- the call sites actually use it -----------------------------------------

def test_every_caller_shares_one_implementation():
    """If any of these drifts back to a local copy, the bugs above return to
    that one output and nowhere else — which is precisely what happened."""
    from src import mcp_tools
    assert mcp_tools._usd is fmt.usd
    assert mcp_tools._big is fmt.big
    assert mcp_tools._title is fmt.district_name


def test_the_briefing_generator_no_longer_rounds_a_third_away():
    from scripts import isd_intel
    assert isd_intel._usd(1_500_000) == "$1.5M"
    assert isd_intel._usd(1_234) == "$1,234"
    assert isd_intel._usd(None) == ""
    assert isd_intel.nice_name("S AND S CISD") == "S and S CISD"

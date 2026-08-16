"""The three receipt-carrying insights: the money clock, your house's share,
and the starkest borders.

Each publishes a claim a future edit could quietly break while the suite
stayed green — the divisor behind the per-second rate, the 500-student
exclusion the borders section asserts in prose, the decimal guard that keeps a
pasted appraisal value from inflating 100x. These tests hold the constants and
the sentences to each other, in the same spirit as the framing tests that lock
the disclosure text.

Static checks on the source, deliberately: the behaviours were verified in a
driven browser when built (the clock counts, 500000/100*1.0138 = 5069 exact,
Cotulla-United = 10,957 exact); what needs standing enforcement is that the
published claims and the code they describe cannot drift apart.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "static" / "index.html").read_text()
GEOMAP = (ROOT / "static" / "geomap.html").read_text()


# ---------------------------------------------------------------- the clock

def test_the_clock_divides_by_a_year_of_seconds_and_says_so():
    """The rate is total spend over 31,536,000 seconds. If the divisor changes,
    the popover's stated divisor must change with it — this asserts both appear
    and agree, so one cannot be edited without the other."""
    assert "31536000" in INDEX, "the divisor is gone"
    assert "31,536,000 seconds" in INDEX, (
        "the popover no longer states the divisor a reader can check")


def test_the_clock_admits_it_is_an_average():
    """The one sentence that keeps the counter honest. Spending is not smooth;
    a counter that presents itself as a meter would be a gimmick wearing a
    statistic's clothes."""
    assert "an average, not a meter" in INDEX


def test_the_clock_ticks_text_only_never_the_markup():
    """Rebuilding innerHTML each second destroyed the '?' button under the
    reader — keyboard focus fell to <body> within a second. The tick may touch
    only the counter's textContent."""
    assert "clock-amt" in INDEX
    assert "amt.textContent = fmtMoney(" in INDEX


# ------------------------------------------------------------- the house bill

def test_a_pasted_appraisal_value_cannot_inflate_100x():
    """'250,000.00' straight off an appraisal-district site must read as
    250000, not 25000000. The decimal point is truncated before the commas are
    stripped."""
    assert "split('.')[0].replace(/[^0-9]/g, '')" in INDEX, (
        "the decimal guard on the home-value input is gone — a value pasted "
        "with cents inflates the bill 100x")


def test_the_bill_prints_its_own_arithmetic():
    """The working travels with the answer: value ÷ 100 × the adopted rate,
    shown beside the dollar figure so the bill is checkable, not oracular."""
    assert "&divide; 100 &times;" in INDEX
    assert "the adopted rate above" in INDEX


def test_the_minutes_claim_names_what_the_total_excludes():
    """The denominator is operating + debt, not all funds — CLAUDE.md's rule
    that the econ total excludes construction. The prose must say so, or a
    building-year district makes the minutes figure quietly overstate."""
    assert "construction excluded" in INDEX


# ---------------------------------------------------------------- the borders

def test_the_borders_exclusion_rule_matches_its_own_prose():
    """The section says districts under 500 students are excluded; the code
    must use the same number. This is the site-wide ranking rule — per-student
    figures in tiny districts move on a single hire."""
    assert "MIN_STUDENTS = 500" in GEOMAP, "the exclusion constant changed or vanished"
    assert "under 500 students are excluded" in GEOMAP, (
        "the section no longer states the exclusion it applies")


def test_a_border_means_a_shared_edge_not_a_corner_touch():
    """'Shares a real boundary line' must mean a line. One shared quantised
    vertex can be a corner touch; the list selects the extreme tail of
    thousands of edges, which is exactly where such artifacts surface."""
    assert "adjStrength[key] || 0) < 2" in GEOMAP


def test_the_gap_is_the_difference_of_the_rounded_figures_shown():
    """A reader subtracting the two displayed numbers must get the displayed
    gap. The builder's own rule: round once and derive the rest."""
    assert "Math.abs(Math.round(ma.s) - Math.round(mb.s))" in GEOMAP

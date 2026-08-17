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


# ------------------------------------------------------------ the news ticker

def test_the_news_ticker_rotates_whole_headlines_and_links_the_feed():
    """The front-page news strip follows the figures strip's settled rule: one
    WHOLE headline at a time, never a crawling marquee fragment, and the full
    stream stays one click away on /feed."""
    assert 'id="newsticker"' in INDEX
    assert 'id="news-track"' in INDEX
    assert '<a class="ticker-all" href="/feed">' in INDEX


def test_news_headlines_are_escaped_before_they_touch_innerhtml():
    """Headlines are external text from news sources. Unescaped, a headline
    containing markup would execute in every reader's browser."""
    assert "replace(/&/g, '&amp;').replace(/</g, '&lt;')" in INDEX


def test_both_strips_share_one_rotator_and_it_honours_reduced_motion():
    """The figures strip and the news strip share a contract, so they must
    share the code — fixing the reduced-motion rule in one and not the other
    is how the three _usd formatters drifted apart. One rotator, two
    callers, and the reduced-motion branch lives only in it."""
    start = INDEX.find("function rotateStrip")
    assert start != -1, "the shared rotator is gone"
    body = INDEX[start:start + 1800]
    assert "prefers-reduced-motion" in body
    assert "classList.add('all')" in body
    assert INDEX.count("rotateStrip(") >= 3      # definition + both callers
    assert INDEX.count("bar.matches(':hover')") == 1, (
        "a second strip rotator exists outside rotateStrip — the "
        "duplication is back")


def test_hidden_actually_hides_a_ticker_strip():
    """An author display:flex beats the UA's [hidden]{display:none}, so a strip
    with nothing to show rendered as an empty visible bar on production
    (owner-reported, screenshot-confirmed). The guard must exist."""
    assert ".ticker[hidden] { display:none !important; }" in INDEX


def test_the_news_strip_reads_briefing_not_a_raw_static_path():
    """The site deliberately has NO blanket static mount — one asset, one
    route — so /static/isd_briefing.json 404s in production. The strip must
    read /briefing, which is CDN-cached and falls back to the committed
    snapshot server-side."""
    assert "fetch('/static/isd_briefing.json')" not in INDEX
    assert "api('/briefing')" in INDEX


def test_briefing_carries_shared_cache_when_the_site_is_public(monkeypatch):
    """Without this header the front-page news strip is one database round
    trip per visit. With SITE_PASSWORD set the header must vanish — a locked
    site must never prime a shared cache."""
    from fastapi.testclient import TestClient

    from src.api import app
    with TestClient(app) as c:
        r = c.get("/briefing")
        if r.status_code == 200:
            assert "s-maxage=3600" in r.headers.get("cache-control", "")


def test_the_brand_is_home_and_never_carries_the_district():
    """The owner asked twice where the brand takes them. It takes them HOME —
    the statewide landing — so it must never be rewritten to /?d=… like the
    view-switching tabs are. Both the parse-time decoration and the
    click-time resolver must skip it, on every page."""
    for page in sorted((ROOT / "static").glob("*.html")):
        html = page.read_text()
        if 'id="masthead"' not in html:
            continue
        assert html.count("a.classList.contains('m-brand')") == 2, (
            f"{page.name}: the brand-is-home exclusion is missing from the "
            f"decoration or the click resolver")


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

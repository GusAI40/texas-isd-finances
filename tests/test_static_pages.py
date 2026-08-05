"""The static pages must actually parse, not merely serve.

A `const` redeclaration once killed static/map.html entirely while the page
still returned 200 and still contained every string you would grep for. These
tests are the guard: they parse the script the way a browser would, and they
assert the structural pieces that a grep-based check would happily miss.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.check_static_js import STATIC, check_page, inline_scripts  # noqa: E402

PAGES = sorted(STATIC.glob("*.html"))

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to parse JavaScript"
)


def test_expected_pages_exist():
    assert {p.name for p in PAGES} == {
        "index.html", "map.html", "geomap.html", "intel.html", "heatmap.html", "feed.html",
        "about.html",
    }


@needs_node
@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_inline_javascript_parses(page):
    err = check_page(page)
    assert err is None, f"{page.name} has a JavaScript syntax error:\n{err}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_have_inline_script(page):
    # If this ever hits zero the parse test above passes vacuously.
    assert inline_scripts(page), f"{page.name} has no inline script to check"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_external_script_or_style(page):
    """The CSP forbids external script. Catch it here rather than in a browser."""
    html = page.read_text(encoding="utf-8")
    for marker in ("cdn.jsdelivr", "unpkg.com", "googleapis.com", "cdnjs."):
        assert marker not in html, f"{page.name} loads from {marker}, which the CSP blocks"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_script_tag_points_at_a_dead_path(page):
    """A same-origin src= slips past both the CSP and a host-based grep.

    /_vercel/insights/script.js sat in two pages while Web Analytics was off,
    so every visitor fetched a 404. Any src= here has to resolve to something
    this repo actually serves.
    """
    import re
    # Strip HTML comments first — a commented-out tag is documentation, not a
    # request. The note explaining why the insights tag was removed contains
    # the tag itself so it can be pasted back.
    html = re.sub(r"<!--.*?-->", "", page.read_text(encoding="utf-8"), flags=re.S)
    srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', html)
    for src in srcs:
        assert not src.startswith("/_vercel/"), (
            f"{page.name} loads {src}, which 404s unless Vercel Web Analytics is enabled"
        )
        if src.startswith("/"):
            assert (STATIC / src.lstrip("/")).exists(), f"{page.name} loads missing {src}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_accessibility_basics(page):
    """Both maps draw to a canvas no screen reader can read, so each carries a
    table twin. The skip link and reduced-motion rule apply to every page."""
    html = page.read_text(encoding="utf-8")
    assert "<html lang=" in html, f"{page.name} declares no language"
    assert "prefers-reduced-motion" in html, f"{page.name} has no reduced-motion rule"
    # A real skip link, not merely the word "skip" — index.html has a tour
    # button labelled Skip, which is what an earlier version of this test
    # accidentally accepted as an accessibility feature.
    assert 'class="skiplink" href="#' in html, f"{page.name} has no skip link"
    assert ".skiplink:focus" in html, f"{page.name}'s skip link never becomes visible"
    if page.name in {"map.html", "geomap.html", "heatmap.html"}:
        assert 'id="a11y-table"' in html, f"{page.name} lost its table twin markup"
        assert "function renderA11yTable" in html, f"{page.name} lost its table twin builder"
        assert "renderA11yTable()" in html, f"{page.name} never calls renderA11yTable"


def test_prototype_url_never_appears():
    """txisd.dev is the citable address; the vercel.app host must not leak."""
    for page in PAGES:
        assert "texas-isd-finances.vercel.app" not in page.read_text(encoding="utf-8")


def test_index_has_flash_free_theme_toggle():
    """Dark mode must be decided before first paint (no flash) and must be a
    real toggle, not just a word. index.html carries the pre-paint script, the
    button, an inverted-text variable for surfaces that sit on --ink, and a
    dark variable block."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "data-theme" in html and ':root[data-theme="dark"]' in html
    assert "tisd_theme" in html                     # persisted choice
    assert "prefers-color-scheme: dark" in html     # follows the device by default
    assert 'id="btn-theme"' in html
    assert "--ink-invert" in html, "text on --ink surfaces needs an inverted color, or it vanishes in dark"
    # The pre-paint theme script must run in <head>, before the body renders.
    head = html.split("</head>")[0]
    assert "data-theme" in head, "theme is applied after <head>, which causes a flash"


def test_ask_footer_names_only_the_llm_actually_used():
    """The ask box must not claim a multi-LLM stack it does not have."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "OpenAI" in html and "LangChain" in html
    for absent in ("Perplexity", "Pinecone", "MongoDB", "Multi-LLM", "GOAT-UIX"):
        assert absent not in html, f"{absent} is not in this stack and must not appear"

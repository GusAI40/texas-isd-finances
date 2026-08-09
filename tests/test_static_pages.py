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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.check_static_js import STATIC, check_page, inline_scripts  # noqa: E402

PAGES = sorted(STATIC.glob("*.html"))

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to parse JavaScript"
)


def test_expected_pages_exist():
    assert {p.name for p in PAGES} == {
        "index.html", "map.html", "geomap.html", "intel.html", "heatmap.html", "feed.html",
        "about.html", "forensics.html",
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
    real toggle, not just a word.

    The palette moved into static/design.css when the design system was
    introduced — one definition instead of seven drifting copies — so the
    token half of this invariant is asserted there. The pre-paint script and
    the button still have to live in the page itself.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "design.css").read_text(encoding="utf-8")
    assert ':root[data-theme="dark"]' in css, "no dark palette in the design system"
    assert "--on-ink" in css, "text on --ink surfaces needs an inverted colour, or it vanishes in dark"
    assert "tisd_theme" in html                     # persisted choice
    assert "prefers-color-scheme: dark" in html     # follows the device by default
    assert 'id="btn-theme"' in html
    # The pre-paint theme script must run in <head>, before the body renders.
    head = html.split("</head>")[0]
    assert "data-theme" in head, "theme is applied after <head>, which causes a flash"
    # design.css must be linked in <head> too: a stylesheet loaded later would
    # paint unstyled content first.
    assert "design.css" in head, "the design system must load before first paint"


DESIGN_CSS = STATIC / "design.css"


def test_no_emoji_anywhere():
    """82 emoji across seven pages were replaced by a drawn icon set. Emoji
    render differently on every platform and carry colour nobody chose; on a
    public-records site they read as unserious. Keep it at zero."""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "design_audit.py"), "--emoji"],
        capture_output=True, text=True)
    assert r.returncode == 0, f"emoji have come back:\n{r.stdout}"


def test_design_tokens_pass_wcag_aa():
    """Every foreground/background pair the system uses must clear AA in BOTH
    themes. A palette that has not been measured is a guess."""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "contrast_check.py")],
        capture_output=True, text=True)
    assert r.returncode == 0, f"contrast failures:\n{r.stdout}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_links_the_design_system(page):
    assert "design.css" in page.read_text(encoding="utf-8"), (
        f"{page.name} does not load the design system, so it will drift"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_do_not_redefine_tokens(page):
    """Seven copies of the palette is what produced three different greens all
    called --good. Tokens belong to design.css alone."""
    import re
    html = page.read_text(encoding="utf-8")
    blocks = re.findall(r":root[^{]*\{([^{}]*)\}", html)
    offenders = [b for b in blocks if "--" in b]
    assert not offenders, (
        f"{page.name} redefines design tokens locally; move them to design.css"
    )


def test_type_scale_is_bounded():
    """The pages carried 45 distinct font sizes, fifteen of them between .78
    and .95rem — differences no reader could see but every maintainer had to
    guess at. Literal sizes are allowed only where the scale genuinely cannot
    express it (fluid clamp() hero type)."""
    import re
    literals = set()
    for page in PAGES:
        for value in re.findall(r"font-size:\s*([^;}\n]+)", page.read_text(encoding="utf-8")):
            v = value.strip()
            if v.startswith("var(") or v.startswith("clamp(") or v.startswith("inherit"):
                continue
            literals.add(v)
    assert len(literals) <= 6, (
        f"{len(literals)} hard-coded font sizes outside the scale: {sorted(literals)}"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_icon_markup_is_never_assigned_via_textcontent(page):
    """textContent cannot render markup — it prints the raw <svg ...> tag on
    screen. Three of these shipped and were invisible until a specific state
    fired (a geolocation callback, the tour's last step), so grep for the
    pattern rather than trusting a screenshot to catch it."""
    import re
    html = page.read_text(encoding="utf-8")
    bad = re.findall(r"(?:textContent|innerText)\s*=[^;\n]*<svg", html)
    assert not bad, (
        f"{page.name} assigns icon markup via textContent; use innerHTML: {bad[:2]}"
    )


def test_icon_sprite_is_present_and_monochrome():
    """Icons must inherit currentColor, or they cannot work in both themes."""
    css = DESIGN_CSS.read_text(encoding="utf-8")
    assert ".ico" in css and "currentColor" in css
    sprite = (STATIC / "_icons.svg").read_text(encoding="utf-8")
    assert sprite.count("<symbol") >= 20, "icon set is too small to replace the emoji"
    # No hard-coded colours in the sprite: every mark takes its colour from context.
    import re
    assert not re.search(r'(fill|stroke)="#', sprite), "icons must not hard-code colour"


def test_chart_png_export_serializes_a_clone_and_reports_failure():
    """"Chart as image" shipped broken and SILENT: the code string-prepended
    xmlns/width onto '<svg', but XMLSerializer already emits xmlns and the
    element already has width="100%" — so the payload had duplicate attributes,
    was invalid XML, the Image fired onerror, and with no onerror handler the
    button did nothing at all. Pin the three properties of the fix."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    fn = html.split("function pngDownload(")[1].split("\n}")[0]
    # 1. Serialize a clone with real attributes — never string-splice '<svg'.
    assert "cloneNode(true)" in fn, "pngDownload must serialize a clone"
    assert "setAttribute('xmlns'" in fn, "xmlns must be set, not prepended"
    assert "replace('<svg'" not in fn, (
        "string-prepending onto '<svg' duplicates attributes and breaks the export"
    )
    # 2. A rasterised SVG inherits nothing, so the var(--x) colours it draws
    #    with must be re-declared on the exported root.
    assert "PNG_VARS" in html and "getPropertyValue" in fn, (
        "CSS variables must be inlined or the exported chart loses its colours"
    )
    # 3. Never fail silently again.
    assert "img.onerror" in fn, "a failed export must tell the reader, not do nothing"


def test_ask_footer_names_only_the_llm_actually_used():
    """The ask box must not claim a multi-LLM stack it does not have."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "OpenAI" in html and "LangChain" in html
    for absent in ("Perplexity", "Pinecone", "MongoDB", "Multi-LLM", "GOAT-UIX"):
        assert absent not in html, f"{absent} is not in this stack and must not appear"

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

# Pages that are NOT part of the public portal. These tests enforce the public
# design system — one masthead, the AI disclosure, shared tokens — and a private
# operations page should carry none of that: it has no public masthead to share,
# and stamping an AI disclosure on a page only the owner can reach would be
# decoration, not disclosure. They are excluded here BY NAME rather than by a
# pattern, so adding a private page is a deliberate edit to this list and can
# never happen by accident. Their JavaScript is still parsed below, because a
# syntax error breaks a private page exactly as badly as a public one.
# Excluded from the PUBLIC design-system checks by name — they carry no
# masthead and are not part of the portal — but they stay in ALL_PAGES, so a
# syntax error still fails the build. A private page breaks just as badly.
PRIVATE_PAGES = {"opsmap.html", "opsintel.html"}

ALL_PAGES = sorted(STATIC.glob("*.html"))
PAGES = [p for p in ALL_PAGES if p.name not in PRIVATE_PAGES]

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to parse JavaScript"
)


def test_expected_pages_exist():
    assert {p.name for p in PAGES} == {
        "index.html", "map.html", "geomap.html", "intel.html", "heatmap.html", "feed.html",
        "about.html", "forensics.html", "sources.html", "transparency.html",
    }


@needs_node
@pytest.mark.parametrize("page", ALL_PAGES, ids=lambda p: p.name)
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
            # Assets are served from the static/ directory under either shape:
            # '/track.js' (a bare route) or '/static/track.js' (the convention
            # design.css uses). Both resolve to the same file on disk.
            rel = src.lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
            assert (STATIC / rel).exists(), f"{page.name} loads missing {src}"


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


def test_the_more_menu_is_not_inside_the_scrolling_tab_strip():
    """The dropdown lived inside .m-tabs, whose overflow-x:auto CLIPS an
    absolutely-positioned child — the menu opened underneath the page and
    every item was unreachable, which read as a dead link (reported by the
    owner, confirmed by elementFromPoint in a driven browser). The details
    element must be a SIBLING of the tab strip, never a child."""
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        if 'class="m-more"' not in html:
            continue
        tabs_start = html.find('class="m-tabs"')
        tabs_end = html.find("</div>", tabs_start)
        more = html.find('<details class="m-more">')
        assert more > tabs_end > tabs_start > -1, (
            f"{page.name}: the More dropdown is back inside the m-tabs "
            f"overflow container, where the container clips it")


def test_clicking_the_tab_for_the_current_page_scrolls_to_top():
    """A same-destination masthead click used to be a silent reload — the
    browser restored the scroll position, so the brand and the active tab
    looked dead. Every page's masthead script must carry the intercept."""
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        if 'id="masthead"' not in html:
            continue
        assert "u.pathname === location.pathname && u.search === location.search" in html, (
            f"{page.name}: the same-destination scroll-to-top intercept is gone")


def test_every_page_carries_the_same_masthead():
    """Singularity: one identical header on every page — brand, the seven
    primary destinations, and a theme toggle — so no reader is ever more
    than one tap from anywhere, and no page is a trap."""
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        assert 'id="masthead"' in html, f"{page.name} lost the masthead"
        for dest in ('href="/feed"', 'href="/forensics"', 'href="/geomap"',
                     'href="/heatmap"', 'href="/about"', 'href="/sources"',
                     'href="/map"', 'href="/intel"', 'href="/transparency"'):
            assert dest in html, f"{page.name} masthead lost {dest}"
        assert 'id="mast-theme"' in html, f"{page.name} masthead lost its theme toggle"


def test_every_page_carries_the_ai_disclosure_line():
    """The owner's rule: hit the truth head-on. Every page ends with the same
    disclosure — AI used across the entire system, margin of error, as-is, use
    at your own risk — linking /transparency, which carries the full legal
    text and the making-of. A page without the line is a page that hides it."""
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        assert 'id="ai-note"' in html, f"{page.name} lost the AI disclosure line"
        assert '/transparency"' in html, f"{page.name} does not link the terms"
        assert "margin of" in html and "own risk" in html, page.name


def test_the_disclosure_is_front_and_center_not_only_a_footnote():
    """Owner's requirement: the AI statement leads, it doesn't hide. The hero
    carries it above the proof row, before any number asks to be believed."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    truth, proof = html.find('id="hero-truth"'), html.find('class="proof"')
    assert truth != -1, "the hero transparency strip is gone"
    assert proof == -1 or truth < proof, "the disclosure sank below the fold"
    strip = html[truth:truth + 600]
    assert "/transparency" in strip and "Built with AI" in strip


def test_the_transparency_page_states_the_essentials():
    """The four commitments the page exists to make, each load-bearing:
    the disclosure, the limits, the liability line, and the invitation to
    verify with an independent AI."""
    html = (STATIC / "transparency.html").read_text(encoding="utf-8")
    assert "Artificial intelligence has been used" in html
    assert "margin of error" in html
    assert "without warranty" in html
    assert "at your own risk" in html
    assert "errors can" in html.lower()          # verification has limits
    assert "/mcp" in html                        # validate with your own LLM
    assert "corrections with credit" in html.lower() or "corrections" in html


def test_index_has_flash_free_theme_toggle():
    """Dark mode must be decided before first paint (no flash) and must be a
    real toggle, not just a word.

    The palette moved into static/design.css when the design system was
    introduced — one definition instead of seven drifting copies — so the
    token half of this invariant is asserted there. The pre-paint script and
    the button still have to live in the page itself.

    Policy changed 2026-08-11 at the owner's request: the site is LIGHT by
    default for everyone. Only an explicit toggle choice ('dark' in
    localStorage) turns dark — the OS preference is no longer consulted, so
    `prefers-color-scheme` must NOT appear in the pre-paint script.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "design.css").read_text(encoding="utf-8")
    assert ':root[data-theme="dark"]' in css, "no dark palette in the design system"
    assert "--on-ink" in css, "text on --ink surfaces needs an inverted colour, or it vanishes in dark"
    assert "tisd_theme" in html                     # persisted choice
    assert "prefers-color-scheme" not in html, (
        "the OS must not decide the theme: light is the default, dark is an "
        "explicit choice")
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


# --- the trust question, asked the way a reader asks it -----------------------

def test_the_trust_question_is_asked_and_answered_in_plain_language():
    """The trust machinery predates this section — /sources, /provenance,
    /transparency, clickable lineage — but it was spread across four pages and
    a click nobody knew to make. This locks the one place that asks the
    reader's actual question and answers all five parts of it: origin,
    checking, corrections, the AI's role, and check-it-yourself. The Wills
    Point correction is named because a real mistake, fixed in public, is the
    strongest trust evidence the site owns."""
    html = (ROOT / "static" / "index.html").read_text()
    assert 'id="trust"' in html
    assert "Can I trust these numbers?" in html
    for must in ("/sources", "/provenance", "/transparency"):
        section = html.split('id="trust"')[1].split("</section>")[0]
        assert must in section, f"the trust section no longer links {must}"
    assert "Wills Point" in html.split('id="trust"')[1].split("</section>")[0], (
        "the public-correction receipt is gone from the trust answer")


# --- the masthead has to be usable on a phone --------------------------------

def test_the_phone_masthead_gives_the_tab_strip_its_own_row():
    """On iPhone width the flexible tab strip was squeezed to a ~56px window
    over 588px of tabs — brand, More and Theme kept the first row and primary
    navigation got the leftovers. Owner-reported as nearly impossible to select
    from; measured in a driven browser (532px of the strip hidden). Below 720px
    the strip must take a full-width second row of its own."""
    css = (STATIC / "design.css").read_text(encoding="utf-8")
    i = css.find("@media (max-width: 720px)")
    assert i != -1, "the phone masthead media query is gone"
    block = css[i:i + 600]
    assert "flex: 1 1 100%" in block, "the tab strip no longer claims a full row"
    assert "order: 10" in block, (
        "without the order the strip wraps between brand and More instead of last")


def test_every_page_asks_for_the_same_design_css_version():
    """The masthead rollout lesson: design.css is cached an hour, so a CSS fix
    ships with a version bump or phones render the old header for an hour. A
    page left on the old version silently serves the bug after everyone else
    is fixed — all pages must cite one identical version string."""
    import re
    versions = {}
    for page in sorted(STATIC.glob("*.html")):
        m = re.search(r"design\.css\?v=(\d+)", page.read_text(encoding="utf-8"))
        if m:
            versions[page.name] = m.group(1)
    assert versions, "no page links a versioned design.css"
    assert len(set(versions.values())) == 1, f"version drift: {versions}"


# --- the intelligence layer is global, not district-gated --------------------

def test_the_ask_box_is_outside_the_district_dashboard():
    """The ask box answers questions about ANY Texas district, but it lived
    inside #dash — the container hidden until a district is picked — so the
    statewide landing had no visible intelligence layer at all and the owner
    could not find it. The ancestor walk (not a grep: position is the claim)
    must never show #dash above it again."""
    import re
    s = (STATIC / "index.html").read_text(encoding="utf-8")
    # Matched by id, not by the whole tag: the sections carry a data-section
    # attribute for engagement tracking now, and a test that pins the exact
    # opening tag fails on an attribute that has nothing to do with position.
    m0 = re.search(r'<section id="ask-section"[^>]*>', s)
    assert m0, "the ask section is gone"
    i = m0.start()
    stack = []
    for m in re.finditer(r'<(/?)(div|section|main|body|details)\b([^>]*)>', s[:i]):
        close, tag, attrs = m.group(1), m.group(2), m.group(3)
        if close:
            for j in range(len(stack) - 1, -1, -1):
                if stack[j][0] == tag:
                    stack.pop(j)
                    break
        else:
            stack.append((tag, attrs))
    assert not any('id="dash"' in attrs for _, attrs in stack), (
        "the ask box is back inside #dash — invisible on the statewide landing")


def test_every_page_offers_ask_a_question_and_hash_links_stay_clean():
    """Owner directive: the ask layer is reachable from every page. Two rules
    travel with the link. A hash link aims at a SECTION, not a view, so it
    never carries ?d — otherwise "Ask" from the statewide landing quietly
    re-enters the stored district, violating home-means-home. And a same-page
    hash click scrolls to the section, not the top."""
    for page in sorted(STATIC.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        if 'id="masthead"' not in html:
            continue
        assert '<a href="/#ask-section">Ask a question</a>' in html, (
            f"{page.name}: the More menu no longer offers the ask layer")
        assert "!u.hash" in html, (
            f"{page.name}: hash links must never carry ?d")
        assert "u.hash.slice(1)" in html, (
            f"{page.name}: a same-page hash click must scroll to the section")
    front = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'class="finder-ask"' in front and 'href="#ask-section"' in front, (
        "the landing lost its visible way into the ask layer — the full box "
        "sits thousands of pixels down; the finder line is the front door")


# --- light is the default, everywhere, and the device never decides ----------

def test_light_is_the_default_and_only_an_explicit_choice_goes_dark():
    """Owner directive: the site opens WHITE. Three layers enforce it and each
    has a real failure behind it: the meta hint was "light dark", which let a
    dark-mode phone paint the pre-CSS canvas and form controls dark on a white
    site (read as "dark is the default"); the boot script must gate dark on a
    SAVED choice, never the OS; and design.css pins the browser's own control
    palette to the chosen theme, covering every toggle path with CSS alone."""
    for page in ALL_PAGES:
        html = page.read_text(encoding="utf-8")
        assert '<meta name="color-scheme" content="light dark">' not in html, (
            f"{page.name}: the meta hint lets the device paint the site dark")
        assert "@media (prefers-color-scheme: dark)" not in html, (
            f"{page.name}: a style block follows the device instead of the toggle")
        if "tisd_theme" in html:
            assert "if (_t === 'dark')" in html, (
                f"{page.name}: dark must require a saved explicit choice")
            assert "prefers-color-scheme: dark)').matches" not in html, (
                f"{page.name}: the boot script consults the OS again")
    css = (STATIC / "design.css").read_text(encoding="utf-8")
    assert "color-scheme: light;" in css
    assert "color-scheme: dark;" in css.split('[data-theme="dark"]', 1)[1]


def test_the_api_docs_page_no_longer_follows_the_device():
    """/docs was the one surface with no toggle that still went dark with the
    OS — the lone counter-example to "the site opens white"."""
    from src.api import _docs_html
    html = _docs_html()
    assert "prefers-color-scheme: dark" not in html
    assert "color-scheme:light" in html


def test_no_third_party_individual_is_named_on_the_public_portal():
    """A partner credit naming a private individual, their employer, their
    phone number and their licence number was removed at the owner's request.
    It is pinned here because that block was footer furniture — the kind of
    markup that gets pasted back from an old copy without anyone re-reading it.

    'Coldwell EL' is deliberately NOT matched: it is a real Texas elementary
    school in TEA's own accountability file, and a blanket ban on the word
    would quietly delete a school from the campus layer.
    """
    for page in ALL_PAGES:
        html = page.read_text(encoding="utf-8").lower()
        for gone in ("michelle sanchez", "coldwell banker",
                     "michellesanchezrealtor", "trec license", "0724260"):
            assert gone not in html, f"{page.name} still names {gone!r}"


def test_the_build_your_own_offer_is_present_and_honest():
    """A commercial line on a civic transparency site earns its place by
    describing the hard part truthfully rather than by selling."""
    for name in ("index.html", "about.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert "mailto:gus@ubntag.com" in html, f"{name} has no way to get in touch"
        assert "traceable back to the record it came from" in html, (
            f"{name}'s offer no longer says what the hard part actually was")
        assert "whether it is worth doing" in html, (
            f"{name}'s offer lost the line that makes it an honest one")

"""Does a person actually SEE the page?

Why this file exists
--------------------
On 2026-08-16 a visual audit found that eight of the sixteen sections on the
district report were rendering at `opacity: 0` on the live site — permanently,
after a full scroll to the bottom. They held their height and their content and
painted nothing. Lost that way: the seventeen-year trend, peer comparison, where
the money goes, payroll vs contracts, who the money serves, the anomaly check,
insights, and the natural-language question box.

Every existing check passed the whole time, and each was doing its job:

    verify_live.py          compares live JSON against committed artefacts
    test_provenance.py      re-derives every headline from the state's own file
    verify_artifacts.py     rebuilds each artefact and diffs it byte for byte
    test_static_pages.py    parses the JavaScript for syntax errors

The data was right. The syntax was right. The page was blank anyway. Nothing in
the suite opened a browser and asked whether a reader could see the result — so
this is that rung, and it is the only one that could have caught it.

The project's boot file already warned that a 200 response proves nothing and
that a UI change must never be verified by grepping the served HTML. This takes
that one step further: a page that PARSES cleanly can still show nothing.

What each test here can and cannot catch
---------------------------------------
Measured, not assumed. I reintroduced the original bug and ran this file:

  * `test_the_reveal_animation_cannot_hide_content_on_its_own` FAILED. It reads
    the stylesheet, needs no browser, and is therefore the actual regression
    test for this defect — it holds on every runner.
  * The browser tests PASSED with the bug present. That is not a flaw in them,
    it is the honest limit of running without a database: the sections that get
    stuck are the database-backed ones, and with no database the page correctly
    removes them (`display:none`) rather than leaving them laid out and
    transparent. There is nothing on screen to catch.

So the browser pass here is a net for the general failure — a section that is
laid out, full height, and painting nothing — and it will see this class of bug
wherever the sections have data. It is not a substitute for the static guard,
and saying otherwise would be the same mistake as a check aimed one file to the
left of the thing it describes.

Skips rather than fails when Playwright or a browser is absent, so it never
blocks a contributor without a browser — but note what that means: on a runner
with no browser the browser tests are INERT (the static guard still runs).
Check a CI run once after wiring it in.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

playwright = pytest.importorskip("playwright.sync_api",
                                 reason="playwright is not installed")

# Playwright's bundled browser may be absent even when the package is present.
_BROWSER = next((p for p in Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome")
                 if p.exists()), None) if Path("/opt/pw-browsers").exists() else None

DISTRICT = "057905"          # Dallas ISD — every section has data


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    """A real server serving this working tree.

    Deliberately started with no SUPABASE_DB_URL: the database-backed sections
    answer 503 and the page must still render every section it can. That is the
    documented promise — the site survives a dead database — and it is also the
    condition under which the reveal bug was worst, because those sections are
    the ones that populate late.
    """
    import tempfile
    port = _free_port()
    log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api:app", "--port", str(port)],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        import urllib.request
        # A local socket, so the proxy must not be consulted. Under the full
        # suite something in the environment had HTTP(S)_PROXY set for the
        # child, and every probe went out to the proxy instead of to 127.0.0.1
        # — which the fixture then reported as "the app did not start". A
        # skip that hides a working app is exactly the silent-pass this file
        # was written to stop, so the opener is built explicitly with no proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(60):
            if proc.poll() is not None:
                log.flush()
                pytest.fail("the app exited during startup:\n"
                            + Path(log.name).read_text()[-1500:])
            try:
                opener.open(url + "/health", timeout=2)
                break
            except Exception:      # noqa: BLE001 — still starting
                time.sleep(0.5)
        else:
            log.flush()
            pytest.fail("the app never answered /health in 30s:\n"
                        + Path(log.name).read_text()[-1500:])
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def page_state(base_url):
    """Load the district report, scroll it the way a reader would, and report
    what is on the screen at the end."""
    if _BROWSER is None:
        pytest.skip("no chromium binary for playwright")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(_BROWSER))
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base_url}/?d={DISTRICT}", wait_until="load", timeout=90000)
        page.wait_for_timeout(4000)

        height, y = page.evaluate("document.body.scrollHeight"), 0
        while y < height:
            page.evaluate(f"window.scrollTo(0,{y})")
            page.wait_for_timeout(120)
            y += 600
            height = page.evaluate("document.body.scrollHeight")
        page.wait_for_timeout(2500)          # let any rescue sweep settle

        state = page.evaluate("""() => {
          const secs = [...document.querySelectorAll('#dash section')];
          // A section the page has deliberately REMOVED — display:none, or
          // collapsed to nothing because this district has no takeover, no
          // turnaround, no data behind that panel — is correct behaviour and
          // must not be flagged. The bug is the other shape: a section that is
          // still laid out, still taking up its full height on the page, and
          // painting nothing. That is the only state a reader experiences as
          // blank space where the analysis should be.
          const ghost = s => {
            const cs = getComputedStyle(s);
            if (cs.display === 'none' || s.offsetHeight < 8) return false;
            return parseFloat(cs.opacity) < 0.5 || cs.visibility === 'hidden';
          };
          return {
            total: secs.length,
            unseen: secs.filter(s => ghost(s) && (s.textContent||'').trim().length > 40)
                        .map(s => s.id || '(unnamed)'),
            overflow: Math.max(0, document.documentElement.scrollWidth
                                  - document.documentElement.clientWidth),
          };
        }""")
        state["errors"] = errors
        browser.close()
        return state


def test_the_page_has_the_sections_it_is_supposed_to_have(page_state):
    assert page_state["total"] >= 12, (
        f"only {page_state['total']} sections rendered — the page did not build")


def test_no_section_with_content_is_invisible_to_a_reader(page_state):
    """THE regression test. Eight sections shipped like this and every other
    check stayed green, because a section at opacity 0 keeps its height, keeps
    its text, and serves a perfect 200."""
    assert not page_state["unseen"], (
        "these sections hold content but are not visible after a full scroll: "
        + ", ".join(page_state["unseen"])
        + " — a reader meets blank space where the analysis should be")


def test_the_page_never_scrolls_sideways(page_state):
    assert page_state["overflow"] == 0, (
        f"{page_state['overflow']}px of horizontal overflow")


def test_the_page_throws_no_javascript_errors(page_state):
    assert not page_state["errors"], page_state["errors"][:3]


def test_the_reveal_animation_cannot_hide_content_on_its_own():
    """A static guard for the same bug, which runs with no browser at all.

    The hidden state must be gated on a class that JavaScript adds — so CSS
    alone can never make a section transparent. If `.reveal` ever goes back to
    setting opacity:0 by itself, a failed observer hides the page again.
    """
    css = (ROOT / "static" / "index.html").read_text()
    assert "#dash section.reveal.armed { opacity:0" in css, (
        "the hidden state must require the JS-applied .armed class")
    assert "#dash section.reveal { opacity:0" not in css, (
        "CSS alone must never be able to hide a section — that is the bug that "
        "took out half the district report")


# --- /docs must not depend on anything outside this origin --------------------

def test_the_api_reference_needs_no_external_asset():
    """It rendered as a BLANK PAGE in production — 200, zero pixels, one console
    error — because FastAPI's built-in Swagger UI loads its script from
    cdn.jsdelivr.net and this site's CSP is `script-src 'self'`. The page is
    linked from the report's footer and documented as the API reference.

    Widening the CSP to admit a third-party script host so a docs page can
    render is the wrong trade on a site that already refused a vendor basemap
    for the same reason. So the built-ins stay off and /docs is built from this
    app's own schema.
    """
    from fastapi.testclient import TestClient

    from src.api import app
    with TestClient(app) as c:
        r = c.get("/docs")
        assert r.status_code == 200
        body = r.text
    assert "cdn.jsdelivr.net" not in body, "the docs page reaches for a CDN again"
    assert "fastapi.tiangolo.com" not in body, "and its favicon is blocked too"
    # Server-rendered: readable with JavaScript disabled, so a blocked script
    # can never blank it again.
    assert "<script" not in body.lower()
    assert body.count("<tr>") > 20, "the endpoint list did not render"


def test_the_builtin_cdn_docs_stay_disabled():
    from src.api import app
    assert app.docs_url is None and app.redoc_url is None, (
        "FastAPI's built-in docs load from a CDN the CSP blocks — leaving them "
        "on serves a blank page at a linked URL")

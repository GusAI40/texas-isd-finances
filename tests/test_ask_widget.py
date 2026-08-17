"""The everywhere ask layer — static/ask.js, the floating button + sheet.

What is at risk is not a crash but a quiet downgrade: the sheet is the
intelligence layer's front door on every page, and each guarantee here was a
deliberate choice — capture-phase interception so the masthead's own resolver
does not double-handle the click, textContent-only answer rendering so a
model's output cannot inject markup, reduced-motion fallbacks so the reveal
never becomes a barrier, and the dialog semantics a screen reader needs.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASK = ROOT / "static" / "ask.js"
JS = ASK.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
def test_the_widget_parses():
    r = subprocess.run(["node", "--check", str(ASK)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_masthead_page_loads_the_widget():
    for page in sorted((ROOT / "static").glob("*.html")):
        html = page.read_text(encoding="utf-8")
        if 'id="masthead"' not in html:
            continue
        assert '<script src="/static/ask.js" defer></script>' in html, (
            f"{page.name} does not load the ask layer")


def test_the_service_actually_serves_the_widget():
    """One asset, one route — there is no blanket static mount, so a page
    referencing /static/ask.js without its route 404s in production while
    every file-based test stays green (the /briefing lesson)."""
    from fastapi.testclient import TestClient

    from src.api import app
    with TestClient(app) as c:
        r = c.get("/static/ask.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")


def test_the_dialog_is_a_dialog():
    assert 'role="dialog"' in JS
    assert 'aria-modal="true"' in JS
    assert "aria-labelledby" in JS
    assert "'Escape'" in JS, "Escape must close the sheet"
    assert "lastFocus" in JS, "focus must return to the opener on close"


def test_screen_readers_hear_the_answer_once_not_word_by_word():
    """The word-reveal mutates the DOM dozens of times per answer. A live
    region on the thread would make a screen reader stutter through the
    fragments, so the thread is NOT live — a visually-hidden region announces
    the complete answer exactly once when it lands."""
    assert 'class="ta-thread" aria-live' not in JS, (
        "the animated thread must never be a live region")
    assert 'class="ta-sr" aria-live="polite"' in JS
    assert JS.count("sr.textContent = text") == 2, (
        "both the reveal path and the instant path must announce the answer")


def test_composing_with_an_ime_never_submits_half_a_question():
    """Enter that commits a Japanese/Chinese/Korean composition must not fire
    the question mid-word — that sends a garbled query and spends a model
    call. The same guard lives on the index page's own ask box."""
    assert "!e.isComposing" in JS
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "e.key === 'Enter' && !e.isComposing" in index


def test_text_on_the_accent_uses_the_token_made_for_it():
    """Dark theme flips --accent to a light blue; hardcoded white text on it
    fails contrast on the reader's own bubble and the Ask button. The design
    system ships --accent-ink for exactly this."""
    # The lineage verdict badges are the one exemption, and they are exempt for
    # a reason rather than by oversight: their backgrounds are fixed dark green
    # / amber / red in BOTH themes (a REFUSED verdict must not go pale when the
    # reader flips to dark), so their text is fixed white to match. Everything
    # painted on --accent must use --accent-ink.
    body = "\n".join(ln for ln in JS.splitlines() if ".ta-badge" not in ln)
    assert "color:#fff" not in body.replace("color:var(--accent-ink, #fff)", "")
    assert JS.count("var(--accent-ink, #fff)") >= 2


def test_reduced_motion_gets_the_answer_instantly():
    assert "prefers-reduced-motion" in JS
    assert "if (reduce) { finish(bub, text); return; }" in JS, (
        "the word-reveal must short-circuit to the full text under "
        "reduced motion")


def test_answers_are_text_never_markup():
    """The model's output is untrusted. Every path that writes an answer into
    the page must go through textContent — the skeleton and caret are the only
    innerHTML writes, and both are constant strings this file owns."""
    assert "if (cls) n.className = cls;" in JS      # el() builds nodes, not markup
    assert "n.textContent = text" in JS
    assert "bub.textContent = text" in JS
    assert "res.body.answer || " in JS
    # the structured renderer has exactly two branches for an inline run, and
    # neither can produce markup
    assert "node.appendChild(el('b', null, r.t))" in JS
    assert "node.appendChild(document.createTextNode(r.t))" in JS
    # the only innerHTML assignments are the widget's own constant strings
    for line in JS.splitlines():
        if ".innerHTML" in line and "=" in line:
            assert "res." not in line and "body" not in line and "answer" not in line, (
                f"a server-derived string reaches innerHTML: {line.strip()}")


def test_the_intercept_wins_the_capture_phase_and_keeps_the_fallback():
    """The links keep their real /#ask-section href — if this file ever fails
    to load they still navigate — and the widget takes the click in the
    CAPTURE phase so the masthead's own bubble-phase resolver never
    double-handles it."""
    assert "}, true);" in JS, "the click intercept is no longer capture-phase"
    assert "stopPropagation" in JS
    assert 'a[href="/#ask-section"]' in JS
    assert "e.metaKey || e.ctrlKey" in JS, "modified clicks must stay native"


def test_grandma_sized_targets_and_type():
    """The bar is a grandmother on a phone: every control at least 44px tall,
    the composer at least 52px, and no text below 16px in the body flow."""
    assert "min-height:52px" in JS
    assert "min-height:44px" in JS
    assert "font:16px" in JS


def test_the_disclosure_travels_with_the_sheet():
    """The sheet is a new AI surface, so the honesty line ships inside it —
    what answers, that it can err, and where the privacy detail lives."""
    assert "can make mistakes" in JS
    assert "/about#privacy" in JS
    assert "official TEA data" in JS


def test_the_renderer_is_exported_so_there_is_only_one_of_them():
    """The landing page has its own inline answer box. It used to have its own
    copy of the answer renderer too, which is exactly how it kept printing the
    model's literal `**bold**` after the sheet had components — two renderers
    means one of them is always the older one."""
    assert "render: function (target, structured, alive)" in JS
    front = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "window.TISDAsk.render(box, r.structured" in front, (
        "the landing page is not drawing the structured answer through ask.js")
    # and it still degrades to plain text if the contract is not there
    assert "streamAnswer(box, text, mine)" in front


def test_the_district_on_screen_travels_with_the_question():
    """Context, not steering: the number goes to the answer builder so the
    figures and follow-ups are about the district the reader is looking at. It
    never reaches the model's query."""
    assert "district_number: districtNumber()" in JS
    assert "/^\\d{6}$/.test(d || '')" in JS      # a 6-digit TEA number or nothing


def test_a_wide_table_scrolls_inside_its_own_box():
    """A table wide enough to push the sheet sideways makes the whole answer
    unreadable on a phone. The overflow belongs to the table, never the page."""
    assert ".ta-tw { margin:.7rem 0 0; overflow-x:auto;" in JS


def test_a_figure_with_no_calculation_is_not_dressed_as_a_button():
    """A control that looks clickable and does nothing is a small lie, and the
    composed total genuinely has no division to open."""
    assert "el(c.metric ? 'button' : 'div', 'ta-card')" in JS


def test_follow_up_chips_ask_the_full_question_not_the_label():
    assert "input.value = f.question;" in JS
    assert "el('button', null, f.label)" in JS

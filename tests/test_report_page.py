"""The shareable campaign report at /report/first-671.

A handout, not a portal page: public by link, unlisted everywhere, and held
to the promise printed in its own footer — no district and no person is
named. That line is what makes the link safe to circulate beyond the room it
was shared in, so it is enforced here rather than trusted.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "static" / "report_first671.html"
HTML = PAGE.read_text(encoding="utf-8")


def test_the_route_serves_the_page_noindexed():
    from fastapi.testclient import TestClient

    from src.api import app
    with TestClient(app) as c:
        r = c.get("/report/first-671")
        assert r.status_code == 200
        assert "noindex" in r.headers.get("x-robots-tag", "")
        assert "671 school leaders" in r.text


def test_it_names_no_district_and_no_person():
    """The footer promises it; the build enforces it. District names, email
    addresses and the identifying funnel details stay in the private ops
    surfaces — this page speaks only in aggregates."""
    assert "no district or individual is named" in HTML
    # CSS at-rules (@media) are the only legitimate @ on the page
    assert "@" not in HTML.replace("@media", ""), "an email address leaked in"
    # the districts the forensic identified, by name or by county
    for name in ("Coolidge", "Mexia", "Moody", "Waco", "Riesel", "Ricardo",
                 "Limestone", "McLennan"):
        assert name not in HTML, f"{name} is named in the shareable report"


def test_it_is_unlisted_everywhere():
    """Public by link means exactly that: reachable by nobody who was not
    handed the URL. No masthead tab, no sitemap entry, no feed item."""
    api = (ROOT / "src" / "api.py").read_text()
    sitemap = api[api.index("async def sitemap"):]
    sitemap = sitemap[:sitemap.index("@app.")]
    assert "first-671" not in sitemap, "the handout is in the sitemap"
    for page in sorted((ROOT / "static").glob("*.html")):
        if page.name == "report_first671.html":
            continue
        assert "first-671" not in page.read_text(encoding="utf-8"), (
            f"{page.name} links the handout — it is meant to be unlisted")


def test_it_carries_no_scripts_and_no_external_anything():
    """A handout must render with zero network dependencies and zero
    execution: nothing to break, nothing to track, nothing the CSP has to
    police. The meta-level noindex also has to survive someone mirroring the
    file without its headers."""
    assert "<script" not in HTML
    assert "googleapis.com" not in HTML and "http" not in HTML.replace(
        "https://txisd.dev", "")
    assert '<meta name="robots" content="noindex' in HTML
    assert "<html lang=" in HTML


def test_the_numbers_match_the_record():
    """The handout simplifies the language, never the figures. These are the
    campaign facts as recorded (watermark + the 2026-08-19 forensic); if a
    new wave changes them, this page must be updated or retired, not left
    quietly stale."""
    for figure in ("671", "653", "13 bounced", "16", "2", "348"):
        assert figure in HTML, f"the handout lost the figure {figure}"
    assert "hasn't been switched on" in HTML, (
        "the zero-replies caveat is the honesty line — it stays until the "
        "reply counter is armed")

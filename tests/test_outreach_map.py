"""The outreach map must not overstate what we measured, or leak who we mailed.

Two failure modes are specific to this page and neither is hypothetical:

1. Rendering unmeasured as negative. 571 emails were sent and only 271 checked
   against the provider. Painting the other 300 red would assert a measurement
   nobody made — the same error as counting an unrated campus as failing.

2. Publishing it. Every dot is a named superintendent and whether they opened
   an email. The rest of the site is deliberately anonymous; this must stay
   behind its own token and must never be reachable without one.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import outreach_map
from src.api import app

ROOT = Path(__file__).resolve().parents[1]


def _build(pool=None, mailing=None):
    return asyncio.run(outreach_map.build(pool, mailing))


# --- the honest states --------------------------------------------------------

def test_sent_but_unchecked_is_unknown_not_unopened():
    """The whole point of the sixth colour."""
    class _C:
        async def fetch(self, sql):
            if "outreach_sent" in sql:
                return [{"district_number": "057905", "sent_at": "2026-08-11T00:00:00Z"}]
            return []
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _P:
        def acquire(self): return _C()

    p = _build(_P(), {"057905"})
    assert p["d"]["057905"]["s"] == "unknown", \
        "a sent-but-unchecked district must not be reported as 'not opened'"
    assert p["meta"]["counts"]["delivered"] == 0


def test_a_district_we_never_emailed_is_not_sent():
    p = _build(None, {"057905"})
    assert p["d"]["057905"]["s"] == "not_sent"


def test_districts_with_no_contact_are_counted_not_drawn_as_skipped():
    """~291 districts have no address. Drawing them as 'not sent yet' would
    read as a choice rather than a gap."""
    p = _build(None, {"057905"})
    assert p["meta"]["no_contact"] > 200
    assert len(p["d"]) == 1


def test_charters_without_a_boundary_are_counted_not_dropped():
    p = _build(None, None)
    assert p["meta"]["no_boundary"] == p["meta"]["districts"] - p["meta"]["plotted"]
    assert p["meta"]["plotted"] > 900


def test_the_limits_travel_with_the_payload():
    """A caveat that stays in a doc is a caveat nobody reads."""
    p = _build(None, None)
    joined = " ".join(p["meta"]["limits"]).lower()
    assert "not 'did not open'" in joined
    assert "cannot be retrofitted" in joined, \
        "wave 1 can never turn green; the payload must say so"


# --- it must not be public ----------------------------------------------------

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_ops_routes_404_without_a_token(client, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "s3cret")
    for path in ("/ops/outreach", "/ops/outreach-data"):
        assert client.get(path).status_code == 404, path
        assert client.get(path + "?token=wrong").status_code == 404, path


def test_ops_routes_404_when_no_token_is_configured(client, monkeypatch):
    """Unconfigured must mean absent, not open."""
    monkeypatch.delenv("OPS_TOKEN", raising=False)
    assert client.get("/ops/outreach-data").status_code == 404
    assert client.get("/ops/outreach-data?token=").status_code == 404


def test_ops_data_is_reachable_with_the_right_token(client, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "s3cret")
    r = client.get("/ops/outreach-data?token=s3cret")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert "meta" in r.json() and "d" in r.json()


def test_the_page_is_not_in_the_sitemap_or_public_nav():
    """It must not be discoverable from the public site."""
    for name in ("index.html", "about.html", "sources.html"):
        p = ROOT / "static" / name
        if p.exists():
            assert "/ops/outreach" not in p.read_text(), \
                f"{name} links to the private ops map"


def test_the_page_declares_noindex():
    s = (ROOT / "static" / "opsmap.html").read_text()
    assert 'name="robots"' in s and "noindex" in s


def test_no_email_address_is_ever_in_the_payload():
    """The map needs districts, not people. An address here would put personal
    contact data in a browser payload for no benefit."""
    p = _build(None, None)
    blob = str(p)
    assert "@" not in blob, "an email address leaked into the map payload"


def test_ops_token_is_not_the_site_password():
    """Reusing SITE_PASSWORD would couple taking this private to taking the
    whole public portal private."""
    src = (ROOT / "src" / "api.py").read_text()
    i = src.index("def _ops_ok")
    assert "SITE_PASSWORD" not in src[i:i + 400]
    assert "OPS_TOKEN" in src[i:i + 400]
    assert "compare_digest" in src[i:i + 400], "token compare must be constant-time"



def test_the_private_page_is_still_js_parsed_by_ci():
    """Excluding it from the PUBLIC design suite must not exclude it from the
    syntax check — a const redeclaration once killed a page that still served
    200 and grepped fine."""
    src = (ROOT / "tests" / "test_static_pages.py").read_text()
    i = src.index("def test_inline_javascript_parses")
    assert "ALL_PAGES" in src[max(0, i - 200):i], \
        "the JS parse test must run over ALL pages, private ones included"
    assert "opsmap.html" in src, "private pages must be listed explicitly"

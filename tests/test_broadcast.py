"""Distribution surface: the Atom feed, the prototype-domain redirect, and
MCP discovery.

Everything here runs offline — the feed builder is a pure function of a
briefing dict, the routes serve from the committed snapshot with no database,
and the vercel.json checks read the file, not the platform.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.api import app, build_atom_feed  # noqa: E402
from src.scanner import is_scanner_path  # noqa: E402

ATOM = "{http://www.w3.org/2005/Atom}"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _fake_briefing(n_findings=3):
    findings = [
        {
            # Deliberately hostile characters: escaping is the whole game.
            "headline": 'Fort Worth ISD calls <bond> election & asks "why"',
            "summary": "Trustees placed a bond on the ballot > $1.2B <script>",
            "published_at": "2026-01-10",
            "district_number": "220905",
            "content_hash": "cd4c8bab1082e60e",
        },
        {
            "headline": "TEA appoints board of managers",
            "summary": "State action announced.",
            "published_at": "2026-01-09",
            "district_number": "161921",
            "content_hash": "aa11",
        },
        {
            # No district resolved: must link the feed page, not guess.
            "headline": "Statewide finance report released",
            "summary": "No single district.",
            "published_at": "2026-01-08",
        },
    ][:n_findings]
    return {"meta": {"run_date": "2026-01-10"}, "top_findings": findings}


# --- the builder, offline ---------------------------------------------------

def test_atom_feed_is_valid_xml_with_escaped_content():
    xml = build_atom_feed(_fake_briefing())
    root = ET.fromstring(xml)          # raises on any unescaped & < > "
    assert root.tag == f"{ATOM}feed"
    assert root.find(f"{ATOM}title").text == "Texas ISD — The Feed"
    assert root.find(f"{ATOM}id").text == "https://txisd.dev/feed"
    entries = root.findall(f"{ATOM}entry")
    assert len(entries) == 3
    # The hostile characters survive the round trip intact.
    assert '<bond> election & asks "why"' in entries[0].find(f"{ATOM}title").text


def test_atom_entries_deep_link_their_district():
    root = ET.fromstring(build_atom_feed(_fake_briefing()))
    entries = root.findall(f"{ATOM}entry")
    links = [e.find(f"{ATOM}link").get("href") for e in entries]
    assert "https://txisd.dev/?d=220905" in links
    assert "https://txisd.dev/?d=161921" in links
    # The unresolved story links the human feed page, never a guessed district.
    assert links[-1] == "https://txisd.dev/feed"


def test_atom_entries_have_required_elements_and_rfc3339_dates():
    root = ET.fromstring(build_atom_feed(_fake_briefing()))
    assert root.find(f"{ATOM}updated").text == "2026-01-10T00:00:00Z"
    for e in root.findall(f"{ATOM}entry"):
        for tag in ("title", "id", "updated", "summary", "link"):
            assert e.find(f"{ATOM}{tag}") is not None, f"entry missing <{tag}>"
        updated = e.find(f"{ATOM}updated").text
        assert "T" in updated and updated.endswith("Z"), updated


def test_atom_feed_caps_at_50_newest():
    briefing = {
        "meta": {"run_date": "2026-02-01"},
        "top_findings": [
            {"headline": f"Story {i}", "summary": "s",
             "published_at": f"2026-01-{(i % 28) + 1:02d}", "content_hash": f"h{i}"}
            for i in range(80)
        ],
    }
    root = ET.fromstring(build_atom_feed(briefing))
    entries = root.findall(f"{ATOM}entry")
    assert len(entries) == 50
    dates = [e.find(f"{ATOM}updated").text for e in entries]
    assert dates == sorted(dates, reverse=True), "entries must be newest first"


def test_atom_entry_ids_are_unique():
    root = ET.fromstring(build_atom_feed(_fake_briefing()))
    ids = [e.find(f"{ATOM}id").text for e in root.findall(f"{ATOM}entry")]
    assert len(ids) == len(set(ids))


# --- the route, DB-free -----------------------------------------------------

def test_feed_xml_route_is_declared():
    assert any(getattr(r, "path", None) == "/feed.xml" for r in app.routes)


def test_feed_xml_serves_atom_from_the_committed_snapshot(client):
    """No database in tests, so a 200 here proves the artifact fallback."""
    res = client.get("/feed.xml")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/atom+xml")
    root = ET.fromstring(res.text)
    assert root.tag == f"{ATOM}feed"
    assert root.findall(f"{ATOM}entry"), "feed served with no entries"


def test_feed_page_advertises_the_atom_feed():
    html = (ROOT / "static" / "feed.html").read_text(encoding="utf-8")
    assert 'rel="alternate" type="application/atom+xml"' in html
    assert 'href="/feed.xml"' in html
    assert 'title="Texas ISD Feed"' in html


# --- vercel.json: redirect yes, rewrites never ------------------------------

def test_vercel_json_redirects_prototype_host_and_has_no_rewrites():
    """A `rewrites` block 404s the whole site (CLAUDE.md invariant); a
    `redirects` block is a different mechanism and safe. The prototype
    vercel.app host must 308 to the citable domain."""
    cfg = json.loads((ROOT / "vercel.json").read_text())
    assert "rewrites" not in cfg, "rewrites silently 404s every route in production"

    redirects = cfg.get("redirects")
    assert redirects, "prototype-domain redirect missing"
    entry = next(r for r in redirects
                 if any(h.get("type") == "host" and
                        h.get("value") == "texas-isd-finances.vercel.app"
                        for h in r.get("has", [])))
    assert entry["source"] == "/(.*)"
    assert entry["destination"] == "https://txisd.dev/$1"
    assert entry.get("permanent") is True, "permanent:true is what makes it a 308"
    # The redirect is host-scoped: without `has`, it would loop txisd.dev onto
    # itself and take the real site down.
    assert all(r.get("has") for r in redirects)


# --- MCP discovery ----------------------------------------------------------

def test_scanner_allows_the_mcp_discovery_path():
    assert not is_scanner_path("/.well-known/mcp.json")
    assert not is_scanner_path("/.well-known/security.txt")
    # The whitelist is exact, not a prefix: everything else stays rejected.
    assert is_scanner_path("/.well-known/mcp.json.bak")
    assert is_scanner_path("/.well-known/anything-else")


def test_well_known_mcp_json_points_at_the_mcp_endpoint(client):
    res = client.get("/.well-known/mcp.json")
    assert res.status_code == 200
    body = res.json()
    server = body["mcpServers"]["texas-isd"]
    assert server["url"] == "https://txisd.dev/mcp"
    assert server["transport"] == "http"
    assert "description" in server
    assert "texas-isd-finances.vercel.app" not in res.text

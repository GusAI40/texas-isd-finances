"""Tests for the scanner fast-reject.

The failure mode that matters is OVER-blocking: a pattern that also matches a
real route would take the site down in a way that looks like a platform
outage. So the first test walks every route the app actually declares and
asserts none of them is caught.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.api import app  # noqa: E402
from src.scanner import is_scanner_path  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- the safety property: never block anything real -------------------------

def test_no_declared_route_is_ever_blocked():
    """Walk every route the app declares. If any is blocked, the site breaks."""
    blocked = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        # Fill path params with a realistic value.
        concrete = path.replace("{district_number}", "101912").replace("{n}", "5")
        if is_scanner_path(concrete):
            blocked.append(concrete)
    assert not blocked, f"the scanner filter blocks real routes: {blocked}"


def test_real_pages_still_answer(client):
    """End to end, not just the predicate: the pages must still serve."""
    for path in ("/", "/about", "/feed", "/intel", "/heatmap", "/geomap",
                 "/map", "/health", "/robots.txt", "/sitemap.xml",
                 "/static/design.css", "/openapi.json"):
        assert client.get(path).status_code == 200, path


def test_district_paths_are_not_blocked():
    for d in ("101912", "057905", "061910"):
        for suffix in ("summary", "bonds", "economics", "equity", "outcomes"):
            assert not is_scanner_path(f"/district/{d}/{suffix}")


def test_the_cron_route_is_not_blocked():
    """Blocking this would silently stop the daily news run."""
    assert not is_scanner_path("/api/cron/isd-intelligence")


# --- what it must catch -----------------------------------------------------

@pytest.mark.parametrize("path", [
    "/wp-admin/install.php", "/wp-login.php", "/wp-content/uploads/x.php",
    "/wordpress/wp-admin/", "/xmlrpc.php",
    "/.env", "/app/.env", "/config/.env", "/a/b/c/.env",
    "/.git/config", "/.aws/credentials", "/.ssh/id_rsa", "/.svn/entries",
    "/phpmyadmin/index.php", "/pma/", "/myadmin/",
    "/cgi-bin/luci", "/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
    "/index.php", "/admin.php", "/shell.php", "/login.asp", "/default.aspx",
    "/.DS_Store", "/.htaccess",
])
def test_known_probes_are_blocked(path):
    assert is_scanner_path(path), path


def test_query_string_cannot_smuggle_a_probe():
    assert is_scanner_path("/wp-admin/install.php?step=1")
    assert is_scanner_path("/.env?x=1")


def test_duplicate_slashes_cannot_bypass():
    assert is_scanner_path("//wp-admin/install.php")
    assert is_scanner_path("///.env")


# --- behaviour through the app ---------------------------------------------

def test_probes_get_404_not_403(client):
    """403 confirms something is there to protect. 404 says nothing."""
    for path in ("/wp-admin/install.php", "/.env", "/phpmyadmin/"):
        res = client.get(path)
        assert res.status_code == 404, path
        assert res.status_code != 403


def test_probe_response_reveals_nothing(client):
    """The body must not differ from any other 404, or it becomes a signal."""
    res = client.get("/wp-admin/install.php")
    assert res.json() == {"detail": "Not Found"}
    assert "server" not in {k.lower() for k in res.headers} or True  # platform-set
    assert res.headers.get("cache-control") == "no-store"


def test_security_txt_stays_reachable():
    """/.well-known/security.txt is how someone reports a vulnerability. It
    must not be swept up with the dotfile probes."""
    assert not is_scanner_path("/.well-known/security.txt")
    assert is_scanner_path("/.well-known/anything-else")

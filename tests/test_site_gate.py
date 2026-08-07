"""Tests for the optional whole-site password gate.

These pin the properties that make the lock safe to ship: it is OFF unless
configured, the daily cron and the health check keep working while it is on,
and turning it off is one environment variable.
"""
import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.api import app  # noqa: E402
from src.site_gate import check_basic_auth, is_open_path, should_block  # noqa: E402

PW = "s3cret-preview"
USER = "txisd"


def basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


@pytest.fixture
def client():
    # The context manager runs the app lifespan, which sets app.state.db_pool.
    with TestClient(app) as c:
        yield c


# --- off by default ---------------------------------------------------------

def test_site_is_public_when_no_password_is_set(monkeypatch):
    """A public-records site must fail OPEN. An unset or blank variable means
    the portal is public, exactly as before this feature existed."""
    monkeypatch.delenv("SITE_PASSWORD", raising=False)
    assert should_block("/", None) is False
    monkeypatch.setenv("SITE_PASSWORD", "   ")       # blank counts as unset
    assert should_block("/", None) is False


def test_pages_are_public_end_to_end_without_the_password(client, monkeypatch):
    monkeypatch.delenv("SITE_PASSWORD", raising=False)
    assert client.get("/health").status_code == 200
    assert client.get("/about").status_code == 200


# --- on when configured -----------------------------------------------------

def test_locked_site_refuses_anonymous_requests(monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", PW)
    for path in ("/", "/about", "/feed", "/geomap", "/districts", "/briefing"):
        assert should_block(path, None) is True, path


def test_locked_site_admits_the_right_password(monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", PW)
    assert should_block("/", basic(USER, PW)) is False


def test_locked_site_rejects_wrong_credentials(monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", PW)
    for header in (basic(USER, "wrong"), basic("nobody", PW),
                   "Basic not-base64!!", "Bearer " + PW, "", "Basic "):
        assert should_block("/", header) is True, header


def test_end_to_end_401_then_200(client, monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", PW)
    r = client.get("/about")
    assert r.status_code == 401
    # The browser needs the challenge header, or it shows raw JSON not a prompt.
    assert r.headers.get("www-authenticate", "").lower().startswith("basic")
    # A locked preview must not be indexed or cached.
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert r.headers.get("cache-control") == "no-store"

    ok = client.get("/about", headers={"Authorization": basic(USER, PW)})
    assert ok.status_code == 200


# --- what must keep working while locked ------------------------------------

def test_health_and_cron_stay_open(monkeypatch):
    """Uptime monitoring must not page anyone over a deliberate lock, and the
    daily news cron (separately authorised by CRON_SECRET) must keep running or
    the feed silently stops updating."""
    monkeypatch.setenv("SITE_PASSWORD", PW)
    assert is_open_path("/health")
    assert is_open_path("/api/cron/isd-intelligence")
    assert should_block("/health", None) is False
    assert should_block("/api/cron/isd-intelligence", None) is False


def test_health_answers_while_the_site_is_locked(client, monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", PW)
    assert client.get("/health").status_code == 200


def test_cron_still_enforces_its_own_secret_when_open(client, monkeypatch):
    """Being exempt from the site lock must NOT make the cron unauthenticated."""
    monkeypatch.setenv("SITE_PASSWORD", PW)
    monkeypatch.setenv("CRON_SECRET", "cron-s3cret")
    assert client.get("/api/cron/isd-intelligence").status_code == 401
    assert client.get("/api/cron/isd-intelligence",
                      headers={"authorization": "Bearer wrong"}).status_code == 401


def test_only_health_and_cron_are_exempt():
    """No other path may be quietly exempt — a hole in the lock is not a lock."""
    for path in ("/", "/about", "/feed", "/intel", "/map", "/geomap", "/heatmap",
                 "/districts", "/stats", "/briefing", "/query", "/docs",
                 "/robots.txt", "/sitemap.xml"):
        assert not is_open_path(path), path


# --- comparison safety ------------------------------------------------------

def test_auth_uses_constant_time_comparison():
    """A plain == leaks the password one character at a time to anyone patient
    enough to measure. Assert the module uses compare_digest."""
    src = (Path(__file__).resolve().parent.parent / "src" / "site_gate.py").read_text()
    assert "compare_digest" in src
    assert check_basic_auth(basic("u", "p"), "u", "p") is True
    assert check_basic_auth(basic("u", "p"), "u", "q") is False


def test_password_is_never_hardcoded():
    """The password lives in the environment, never in the repository — so
    rotating it is an env-var change, and git history never carries it."""
    root = Path(__file__).resolve().parent.parent
    src = (root / "src" / "site_gate.py").read_text()
    assert "SITE_PASSWORD" in src, "the password must come from the environment"
    # No string literal is ever compared against as the password.
    assert 'SITE_PASSWORD", "' not in src, "no default password may be baked in"
    # And the real password must not appear anywhere in the tracked tree.
    for path in (root / "src").rglob("*.py"):
        assert "txisd1000" not in path.read_text(), path
    for path in (root / "static").glob("*.html"):
        assert "txisd1000" not in path.read_text(), path

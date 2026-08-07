"""Tests for first-party usage counting.

These pin the PRIVACY guarantees the site makes publicly, not just the
behaviour: a district number never becomes a metric, a referrer never keeps its
query string, a user-agent never survives as anything but a coarse bucket, and
bots never count as visitors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.analytics import (  # noqa: E402
    MAX_QUESTION_CHARS,
    clean_question,
    countable_path,
    device_of,
    is_bot,
    referrer_host,
)

# --- what counts as a page view -------------------------------------------

def test_only_real_pages_are_counted():
    for p in ("/", "/about", "/feed", "/intel", "/heatmap", "/geomap", "/map"):
        assert countable_path(p) == p
    for p in ("/districts", "/health", "/district/101912/summary",
              "/favicon.ico", "/wp-admin/install.php", "/app/.env", "/robots.txt"):
        assert countable_path(p) is None, p


def test_the_district_a_reader_looked_at_is_never_stored():
    """'/?d=101912' must count as '/' — which district someone read is their
    business, not a metric."""
    assert countable_path("/?d=101912") == "/"
    assert countable_path("/geomap?d=057905") == "/geomap"


def test_trailing_slash_does_not_split_the_counter():
    assert countable_path("/about/") == "/about"
    assert countable_path("/") == "/"


def test_invented_paths_cannot_inflate_the_table():
    """An allowlist means a scanner making up URLs cannot create rows."""
    for p in ("/" + "x" * 200, "/../../etc/passwd", "/%2e%2e/", "/a/b/c/d"):
        assert countable_path(p) is None


# --- bots are not visitors --------------------------------------------------

def test_known_bots_are_excluded():
    for ua in ("Mozilla/5.0 (compatible; Googlebot/2.1)",
               "curl/8.4.0", "python-requests/2.31", "Scrapy/2.11",
               "HeadlessChrome/120", "facebookexternalhit/1.1", "zgrab/0.x"):
        assert is_bot(ua), ua


def test_missing_user_agent_is_treated_as_a_bot():
    """Every real browser sends one; the scanners hitting this site often don't."""
    assert is_bot(None) and is_bot("") and is_bot("   ")


def test_real_browsers_are_not_bots():
    for ua in ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
               "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
               "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"):
        assert not is_bot(ua), ua


# --- user-agent never survives as more than a bucket ------------------------

def test_device_is_a_coarse_bucket_only():
    iphone = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148")
    ipad = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    mac = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "Chrome/120.0 Safari/537.36")
    assert device_of(iphone) == "mobile"
    assert device_of(ipad) == "tablet"
    assert device_of(mac) == "desktop"
    assert device_of(None) == "other"
    # The value stored must be one of four fixed buckets — never the string.
    for ua in (iphone, ipad, mac, None):
        assert device_of(ua) in {"mobile", "tablet", "desktop", "other"}


# --- referrers keep the host and nothing else -------------------------------

def test_referrer_keeps_only_the_host():
    """A full referrer URL can carry a query string, and query strings carry
    personal data. Only the host may survive."""
    got = referrer_host("https://www.google.com/search?q=my+kid+school+taxes&uid=abc123")
    assert got == "google.com"
    assert "search" not in got and "uid" not in got and "?" not in got


def test_self_referral_is_dropped():
    assert referrer_host("https://txisd.dev/feed", own_host="txisd.dev") == ""
    assert referrer_host("https://txisd.dev/about", own_host="www.txisd.dev") == ""


def test_direct_visit_has_no_referrer():
    assert referrer_host(None) == ""
    assert referrer_host("") == ""
    assert referrer_host("not a url") == ""


# --- questions -------------------------------------------------------------

def test_question_is_normalised_and_bounded():
    assert clean_question("  how   many\n districts?  ") == "how many districts?"
    long_q = "a" * (MAX_QUESTION_CHARS + 500)
    assert len(clean_question(long_q)) == MAX_QUESTION_CHARS


def test_empty_question_is_not_stored():
    assert clean_question(None) == ""
    assert clean_question("   ") == ""


# --- the guarantee itself ---------------------------------------------------

def test_analytics_module_reads_nothing_identifying():
    """The module must never touch an IP, a cookie, or a session. If this ever
    fails, the site's published privacy promise has been broken in code."""
    src = (Path(__file__).resolve().parent.parent / "src" / "analytics.py").read_text()
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    code = code.split('"""')[0] + '"""'.join(code.split('"""')[2:])  # drop module docstring
    for banned in ("x-forwarded-for", "x-real-ip", "remote_addr", "client.host",
                   "cookie", "set-cookie", "session"):
        assert banned not in code.lower(), f"analytics must not handle {banned}"

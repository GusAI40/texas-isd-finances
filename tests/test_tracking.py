"""The fence around per-recipient tracking.

Every test here exists because the feature is only defensible if its limits
hold. The important ones are the refusals: an anonymous visitor must never
become identified, a forged token must never be stored, and the public
disclosure must exist — shipping the tracking without the sentence is the
failure mode that would make the site's own privacy note a lie.
"""
from __future__ import annotations

import re
from pathlib import Path

from src import tracking

ROOT = Path(__file__).resolve().parent.parent


# --- the fence: who gets tracked at all ------------------------------------

def test_anonymous_visitor_is_never_tracked():
    """No cookie and no token in the URL means None — the caller then leaves
    them to the daily aggregate counters and writes nothing identified."""
    assert tracking.resume_or_start(None, None) is None
    assert tracking.resume_or_start("", "") is None


def test_junk_cookie_does_not_create_an_identity():
    for junk in ("garbage", "a.b", "a.b.c", "...", "x.y.z.notanumber",
                 "'; DROP TABLE visitor_event--.a.b.1"):
        assert tracking.resume_or_start(junk, None) is None


def test_a_forged_token_shape_is_refused():
    """The rid is attacker-controlled in transit. Anything off the shape is
    dropped here, long before it reaches SQL."""
    for bad in ("", None, "short", "a" * 200, "has spaces", "semi;colon",
                "../../etc/passwd", "<script>", "tok'en"):
        assert tracking.valid_token(bad) == ""


def test_a_minted_token_survives_the_round_trip():
    rid = tracking.new_rid()
    assert tracking.valid_token(rid) == rid
    assert len(rid) >= 16          # unguessable is the only protection


# --- sessions: what makes a "return visit" ---------------------------------

def test_clicking_the_email_binds_the_browser():
    rid = tracking.new_rid()
    bound = tracking.resume_or_start(None, rid)
    assert bound is not None
    assert bound[0] == rid
    assert bound[3] is True        # a first sitting is a new session


def test_same_sitting_keeps_one_session():
    rid, visitor, session = tracking.new_rid(), tracking.new_visitor_id(), tracking.new_session_id()
    cookie = tracking.build_cookie(rid, visitor, session, now=1000)
    got = tracking.resume_or_start(cookie, None, now=1000 + 60)
    assert got == (rid, visitor, session, False)


def test_a_later_visit_is_a_new_session_but_the_same_person():
    """The return visit is the whole point: same visitor id, new session."""
    rid, visitor, session = tracking.new_rid(), tracking.new_visitor_id(), tracking.new_session_id()
    cookie = tracking.build_cookie(rid, visitor, session, now=1000)
    got = tracking.resume_or_start(
        cookie, None, now=1000 + tracking.SESSION_GAP_SECONDS + 1)
    assert got is not None
    assert got[0] == rid and got[1] == visitor      # same person
    assert got[2] != session and got[3] is True     # new sitting


def test_two_recipients_on_one_machine_do_not_merge():
    """A superintendent forwarding the link to a colleague on a shared PC must
    not have the colleague's reading recorded as their own."""
    first, second = tracking.new_rid(), tracking.new_rid()
    cookie = tracking.build_cookie(first, tracking.new_visitor_id(),
                                   tracking.new_session_id(), now=1000)
    got = tracking.resume_or_start(cookie, second, now=1010)
    assert got is not None
    assert got[0] == second
    assert got[3] is True          # fresh visitor, fresh session


# --- dwell: the client is not trusted --------------------------------------

def test_absurd_dwell_is_dropped_not_averaged():
    assert tracking.clean_dwell(-1) is None
    assert tracking.clean_dwell(0) is None
    assert tracking.clean_dwell(tracking.MAX_DWELL_MS + 1) is None
    assert tracking.clean_dwell("not a number") is None
    assert tracking.clean_dwell(None) is None
    assert tracking.clean_dwell(4500) == 4500


def test_client_ip_takes_the_leftmost_forwarded_hop():
    assert tracking.client_ip("203.0.113.9, 70.41.3.18", None) == "203.0.113.9"
    assert tracking.client_ip(None, "198.51.100.4") == "198.51.100.4"
    assert tracking.client_ip(None, None) is None


# --- the disclosure must ship with the feature -----------------------------

def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_the_privacy_page_admits_the_exception():
    """If tracking exists and this text does not, the site is lying to its
    readers. That is worse than not shipping the feature."""
    about = _text("static/about.html").lower()
    assert "exception" in about
    assert "email we sent you" in about or "people we emailed" in about
    assert "delete" in about                 # and how to get out of it


def test_the_front_page_no_longer_claims_it_never_measures_a_visitor():
    """The old blanket sentence must not survive verbatim — it is now false."""
    index = _text("static/index.html")
    assert "We measure the site, never the visitor: no cookies" not in index
    assert "measured individually" in index


def test_every_tracked_page_loads_the_beacon():
    for page in ("index", "about", "feed", "forensics", "sources",
                 "intel", "heatmap", "geomap", "map"):
        assert 'src="/static/track.js"' in _text(f"static/{page}.html"), page


def test_the_beacon_is_inert_without_the_server_flag():
    """The script must not run for anonymous visitors, and must never see the
    identity: the rid lives in an httpOnly cookie the page cannot read."""
    js = _text("static/track.js")
    assert 'indexOf("txj_on=1") === -1) return' in js
    assert "rid" not in re.sub(r"/\*.*?\*/", "", js, flags=re.S)


def test_the_tracked_email_says_so():
    """Both halves of the message must carry the disclosure when a token is
    attached — and neither may carry it when one is not."""
    src = _text("scripts/send_outreach.py")
    assert "carries a code unique to you" in src
    assert src.count("carries a code unique to you") == 2   # html + text
    assert 'if rid else ""' in src

"""Per-recipient journey tracking for outreach campaigns.

This is the deliberate exception to `analytics.py`, which measures the site and
never the visitor. Here we measure a named visitor — but only one kind, and
only after they act:

    a person we mailed, who clicked the link we mailed them.

The entry condition is a `?rid=` token that we minted and put in exactly one
email. Nothing else opens the door: no fingerprint, no IP match, no probabilistic
identity. An anonymous visitor cannot fall into this system by accident, and a
tracked visitor is tracked because they followed a link in a commercial message
that identifies its sender and carries an unsubscribe.

Once bound, a first-party cookie carries the token forward, which is what makes
"did they come back next week" answerable. The cookie holds the token, a visitor
id and the current session id — no personal data; the token is only a name in
`outreach_recipient`, which lives in the database behind the service role.

Two things this module does NOT do, on purpose:

  * It never mints a token for someone who arrived without one. Anonymous stays
    anonymous — that path still goes to `analytics.py` and its daily counters.
  * It never reads a rid that isn't well-formed. The token is
    attacker-controlled in transit, and the database has a foreign key to a
    minted row, so a forged value is rejected rather than stored.
"""
from __future__ import annotations

import ipaddress
import re
import secrets
import time

# A browsing "sitting". A gap longer than this starts a new session, which is
# how a return visit is distinguished from a long read.
SESSION_GAP_SECONDS = 30 * 60

# Cookie the tracked visitor carries. First-party, lax, two years — long enough
# that "did the superintendent come back in the autumn" has an answer.
COOKIE_NAME = "txj"
COOKIE_MAX_AGE = 2 * 365 * 24 * 3600

# Tokens are urlsafe-base64 from `secrets`. Bound the shape so a junk or
# injected value is dropped before it reaches SQL or the cookie jar.
_TOKEN_RE = re.compile(r"\A[A-Za-z0-9_-]{8,64}\Z")

# A single page view can't sanely last longer than this; anything above is a
# tab left open over lunch, not reading, and would poison the dwell average.
MAX_DWELL_MS = 30 * 60 * 1000

# Must stay in step with the CHECK constraint on visitor_event (see
# src/migrations.py). This set is the app-side gate; the constraint is the
# database's. Two fences, because a typo'd event name that passes the first one
# should fail loudly at the second rather than accumulate a category nobody
# queries.
EVENTS = frozenset({"email_open", "click", "pageview", "dwell", "question",
                    "return", "section", "followup", "download", "reply"})

# What a client is allowed to assert. The rest are written server-side from
# facts the browser cannot fake: a page it actually requested, a pixel it
# actually fetched, a question the engine actually answered.
CLIENT_EVENTS = frozenset({"section", "download", "followup"})


def new_rid() -> str:
    """A per-recipient, per-campaign token. Unguessable: the only protection
    against someone else's stream being polluted is that they cannot find the
    token, so this is 16 bytes, not a counter or a hash of the email."""
    return secrets.token_urlsafe(16)


def new_visitor_id() -> str:
    return secrets.token_urlsafe(12)


def new_session_id() -> str:
    return secrets.token_urlsafe(9)


def valid_token(token: str | None) -> str:
    """The token if it is well-formed, '' otherwise. Every entry point runs
    through here — query string, cookie and beacon body alike."""
    if not token:
        return ""
    token = token.strip()
    return token if _TOKEN_RE.match(token) else ""


def clean_dwell(ms: object) -> int | None:
    """Milliseconds on a page, or None if the client sent something absurd.
    The beacon body is attacker-controlled; a negative or week-long dwell is
    dropped rather than averaged in."""
    try:
        value = int(ms)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value <= 0 or value > MAX_DWELL_MS:
        return None
    return value


def parse_cookie(raw: str | None) -> tuple[str, str, str, int]:
    """Unpack 'rid.visitor.session.last_seen' -> (rid, visitor, session, ts).

    Returns empty strings when the cookie is absent or malformed, so a caller
    can treat "no cookie" and "junk cookie" identically.
    """
    if not raw:
        return "", "", "", 0
    parts = raw.split(".")
    if len(parts) != 4:
        return "", "", "", 0
    rid, visitor, session = (valid_token(p) for p in parts[:3])
    if not (rid and visitor and session):
        return "", "", "", 0
    try:
        last_seen = int(parts[3])
    except ValueError:
        return "", "", "", 0
    return rid, visitor, session, last_seen


def build_cookie(rid: str, visitor: str, session: str, now: int | None = None) -> str:
    """The cookie value. Deliberately opaque and free of personal data — the
    token becomes a person only by joining `outreach_recipient`."""
    stamp = int(time.time()) if now is None else now
    return f"{rid}.{visitor}.{session}.{stamp}"


def resume_or_start(
    cookie_value: str | None,
    url_rid: str | None,
    now: int | None = None,
) -> tuple[str, str, str, bool] | None:
    """Decide who this request belongs to.

    Returns (rid, visitor_id, session_id, is_new_session), or None when the
    visitor is anonymous — which is the common case and must stay untracked.

    The rules, in order:
      1. A valid ?rid= in the URL always wins. That is the click from the email,
         and it (re)binds the browser to that recipient.
      2. Otherwise the cookie carries a previous binding forward.
      3. No token anywhere means an anonymous visitor: return None and let the
         aggregate counter handle them.
    """
    stamp = int(time.time()) if now is None else now
    c_rid, c_visitor, c_session, last_seen = parse_cookie(cookie_value)
    fresh_rid = valid_token(url_rid)

    rid = fresh_rid or c_rid
    if not rid:
        return None

    # A different recipient's link opened in the same browser starts a clean
    # visitor: two superintendents sharing a machine must not merge into one.
    if fresh_rid and c_rid and fresh_rid != c_rid:
        return rid, new_visitor_id(), new_session_id(), True

    visitor = c_visitor or new_visitor_id()
    if c_session and (stamp - last_seen) <= SESSION_GAP_SECONDS:
        return rid, visitor, c_session, False
    return rid, visitor, new_session_id(), True


def client_ip(forwarded_for: str | None, fallback: str | None) -> str | None:
    """The client address from Vercel's X-Forwarded-For, which is a chain —
    the left-most entry is the real client, the rest are proxies.

    Anything that is not actually an address returns None rather than being
    passed through. The column is `inet`, so a hostname reaches asyncpg and
    raises — and because every tracking write fails open, the result is that
    the ENTIRE event is silently dropped over a field nobody reads. Losing a
    superintendent's click to protect an IP address we do not use is the wrong
    trade in both directions. Found by running the real flow against real
    Postgres: the harness sends a hostname and every click, page view and
    email open vanished with only a warning in a log nobody was reading.
    """
    candidate = None
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            candidate = first
    candidate = candidate or fallback or None
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate

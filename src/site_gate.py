"""Optional password gate for the whole site.

Why this exists
---------------
Before a public launch it is useful to show the site to a few people without
showing it to everyone. Setting SITE_PASSWORD turns the entire portal into a
private preview; unsetting it makes the site public again. No code change, no
redeploy of anything but an environment variable — because the day this
transparency portal goes public, the lock has to come off in one step.

Deliberate choices
------------------
- **Off by default.** With SITE_PASSWORD unset the site behaves exactly as
  before. A misconfigured deploy fails OPEN (public), never closed-and-broken,
  because this is a public-records site and silence looks like censorship.
- **Two paths stay open.** /health, so uptime monitoring does not page someone
  at 3am over a deliberate lock, and the daily cron, which carries its own
  CRON_SECRET bearer and would otherwise stop collecting news the moment the
  lock went on. Neither reveals district data.
- **Constant-time comparison.** A naive `==` leaks the password one character
  at a time to anyone willing to measure. secrets.compare_digest does not.
"""
from __future__ import annotations

import base64
import binascii
import os
import secrets

# Paths that must work even while the site is locked. Neither exposes any of
# the portal's data: one reports liveness, the other is separately authorised.
OPEN_PATHS = frozenset({"/health"})
OPEN_PREFIXES = ("/api/cron/",)


def gate_password() -> str:
    """The configured password, or '' when the site is public."""
    return (os.getenv("SITE_PASSWORD") or "").strip()


def gate_username() -> str:
    """Browsers demand a username field; the password is what actually gates."""
    return (os.getenv("SITE_USERNAME") or "txisd").strip()


def is_open_path(path: str) -> bool:
    route = (path or "").split("?")[0]
    return route in OPEN_PATHS or route.startswith(OPEN_PREFIXES)


def check_basic_auth(header: str | None, username: str, password: str) -> bool:
    """Validate an HTTP Basic `Authorization` header without leaking timing."""
    if not header:
        return False
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        raw = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    user, sep, supplied = raw.partition(":")
    if not sep:
        return False
    # Compare BOTH, always, so the answer takes the same time either way.
    ok_user = secrets.compare_digest(user, username)
    ok_pass = secrets.compare_digest(supplied, password)
    return ok_user and ok_pass


def should_block(path: str, auth_header: str | None) -> bool:
    """True when this request must be refused with a 401 challenge."""
    password = gate_password()
    if not password:
        return False                      # no password configured: site is public
    if is_open_path(path):
        return False
    return not check_basic_auth(auth_header, gate_username(), password)

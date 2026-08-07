"""First-party, privacy-preserving usage counting.

The rule this module exists to enforce: measure the SITE, never the visitor.

What that means concretely — and what the site's published privacy note
promises — is that nothing here can be traced back to a person:

- No IP address is read or stored.
- No full user-agent is stored; it is reduced to 'mobile' / 'desktop' / 'other'
  and then discarded.
- No cookie, session id, visitor id, or fingerprint is set or derived.
- Referrers are reduced to a bare host ('google.com'). A full referrer URL can
  carry a query string, and query strings carry personal data.
- Page views are stored as DAILY COUNTERS, not events. There is no row per
  visit and no timestamp finer than the date, so two visitors on the same day
  are arithmetically indistinguishable.

Bot traffic is excluded on purpose. Half of this site's real traffic is an
exploit scanner hammering /wp-admin/install.php; counting that as "visitors"
would make the numbers a lie.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# Only real pages are counted. API endpoints, assets and probes are not
# "visits", and an allowlist means a scanner inventing paths cannot inflate the
# table (or fill it — the primary key is bounded by this set).
PAGE_PATHS = frozenset({
    "/", "/about", "/feed", "/intel", "/heatmap", "/geomap", "/map",
})

# Substrings that mark an automated client. Deliberately broad: a missed bot
# inflates the visitor count, while a human misread as a bot costs one tick.
_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|curl|wget|python-requests|httpx|axios|okhttp|"
    r"headless|phantom|scrapy|monitor|uptime|pingdom|lighthouse|preview|"
    r"facebookexternalhit|whatsapp|telegram|discord|vercel-screenshot|"
    r"go-http-client|java/|libwww|scanner|nuclei|zgrab|masscan",
    re.I,
)

_MOBILE_RE = re.compile(r"iphone|ipod|android.*mobile|windows phone|mobile safari", re.I)
_TABLET_RE = re.compile(r"ipad|android(?!.*mobile)|tablet", re.I)

MAX_QUESTION_CHARS = 500


def is_bot(user_agent: str | None) -> bool:
    """True for automated clients. An empty UA is treated as a bot: every real
    browser sends one, and the scanners hitting this site often do not."""
    if not user_agent or not user_agent.strip():
        return True
    return bool(_BOT_RE.search(user_agent))


def device_of(user_agent: str | None) -> str:
    """Reduce a user-agent to a coarse category, then forget the rest.

    Three buckets is all that is needed to answer "is this site usable on a
    phone?", and three buckets cannot identify anyone — unlike the full string,
    which is a well-known fingerprinting vector.
    """
    if not user_agent:
        return "other"
    if _TABLET_RE.search(user_agent):
        return "tablet"
    if _MOBILE_RE.search(user_agent):
        return "mobile"
    return "desktop"


def referrer_host(referer: str | None, own_host: str | None = None) -> str:
    """The bare host a visitor arrived from, or '' for direct/self.

    Only the host survives: a full referrer URL can carry a query string, and
    query strings carry personal data. Self-referrals (internal navigation) are
    dropped so they do not drown out real external sources.
    """
    if not referer:
        return ""
    try:
        host = (urlsplit(referer).hostname or "").lower()
    except ValueError:
        return ""
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if own_host:
        own = own_host.lower().split(":")[0]
        if own.startswith("www."):
            own = own[4:]
        if host == own:
            return ""            # internal navigation is not a referral
    return host[:120]


def countable_path(path: str) -> str | None:
    """The page route to count, or None if this request is not a page view.

    The query string is dropped before matching, so '/?d=101912' counts as '/'
    — the district number a reader looked at is their business, not a metric.
    """
    route = (path or "").split("?")[0].split("#")[0]
    if len(route) > 1 and route.endswith("/"):
        route = route.rstrip("/") or "/"
    return route if route in PAGE_PATHS else None


def clean_question(question: str | None) -> str:
    """Normalise a question for storage: collapse whitespace and bound length.

    The text is stored as typed apart from that. It is never joined to anything
    identifying, because nothing identifying is collected in the first place.
    """
    if not question:
        return ""
    q = re.sub(r"\s+", " ", question).strip()
    return q[:MAX_QUESTION_CHARS]

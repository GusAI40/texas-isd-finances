"""Turn away automated vulnerability scanners before doing any work.

Roughly half this site's raw traffic is a bot probing for WordPress installs
and leaked credential files — 99 requests a day to /wp-admin/install.php alone,
and about 210 of the ~430 daily requests are 404s from that one scanner. None
of it can succeed: there is no WordPress here, no .env is served, and the data
artefacts are not exposed. The 404s were always correct.

What they were not was cheap or quiet. Each probe spun up a serverless
function, ran the middleware stack, and wrote a log line — so real errors sat
buried in scanner noise, which is the expensive part. Recognising these paths
first and returning immediately keeps the logs readable and stops paying to
route requests that can only ever 404.

Two rules this must never break:

1. **It may never block a real route.** A test walks every route the app
   declares and asserts none of them matches. Over-blocking would take the site
   down in a way that looks like a platform outage.
2. **It returns 404, not 403.** A 403 confirms something is there to protect;
   404 says nothing at all, which is what an attacker should learn.
"""
from __future__ import annotations

import re

# Segments and suffixes that only appear in attacks against software this site
# does not run. Anchored deliberately: `/wp-` matches /wp-admin and /wp-login
# without matching a legitimate path that merely contains "wp".
_SCANNER_RE = re.compile(
    r"""^/(?:
          wp-|wordpress/|xmlrpc\.php            # WordPress: not used here
        | phpmyadmin|pma/|myadmin                # phpMyAdmin
        | cgi-bin/                               # CGI: nothing is served this way
        | vendor/|composer\.|autoload            # PHP dependency trees
        | \.well-known/(?!security\.txt)         # keep security.txt reachable
        | (?:[^/]+/)*\.(?:env|git|aws|ssh|svn|hg|htpasswd|htaccess|DS_Store)
                                                 # dotfiles at ANY depth
        | (?:[^/]+/)*(?:\.env|config\.php|shell|backup\.sql|dump\.sql)\b
        | (?:[^/]+/)*[^/]*\.(?:php|asp|aspx|jsp|cgi|cfm)$
                                                 # this app serves no such files
      )""",
    re.IGNORECASE | re.VERBOSE,
)


def is_scanner_path(path: str) -> bool:
    """True for a path that can only be an automated probe.

    The query string is dropped first, so `?` tricks cannot smuggle a probe
    past the check.
    """
    route = (path or "/").split("?")[0].split("#")[0]
    # Normalise duplicate slashes: //wp-admin/ should not slip through.
    route = re.sub(r"/{2,}", "/", route)
    if not route.startswith("/"):
        route = "/" + route
    return bool(_SCANNER_RE.match(route))

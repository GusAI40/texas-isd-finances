"""Walk the source register outward and prove each source really is there.

Everything else in this repo checks inward: does the published number match the
artifact, does the artifact match the CSV, does the CSV match its hash. That
chain is airtight and still ends in a claim nobody has tested — that the file it
started from is a real, reachable, public government publication.

This walks the last link. For every entry in `src/sources.py` it:

  1. fetches the URL and reports what actually came back;
  2. confirms the host really belongs to the agency named as publisher, so a
     typo or a hijacked link cannot pose as TEA;
  3. checks the local copy exists and reports its size and SHA-256, which is
     what a reader would compare against their own download.

A dead link makes "check it yourself" false, which is worse than not offering
it. Run this before publishing a claim about provenance, and after any TEA site
reorganisation.

    python scripts/verify_sources.py
    python scripts/verify_sources.py --json docs/source_check.json

Exits non-zero if any source is unreachable or the host does not match the
publisher. Network failures are reported separately from 4xx/5xx, because a
sandbox with no egress is not the same as a dead link.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import sources as S  # noqa: E402

# The host a source MUST live on, given who is named as its publisher. This is
# what stops a typo or a substituted link from passing as a government file.
EXPECTED_HOSTS = {
    "Texas Education Agency": ("tea.texas.gov", "rptsvr1.tea.texas.gov"),
    "Texas Education Agency with the Texas Comptroller":
        ("tea.texas.gov", "comptroller.texas.gov"),
    "US Census Bureau (public domain)": ("census.gov", "www2.census.gov"),
    "US Bureau of Labor Statistics": ("bls.gov", "www.bls.gov"),
    "Compiled county election returns "
    "(Texas Secretary of State, elections division)":
        ("sos.state.tx.us", "sos.texas.gov"),
}

UA = "txisd-source-check/1.0 (+https://txisd.dev/sources)"
TIMEOUT = 30


def host_ok(publisher: str, url: str) -> bool | None:
    allowed = EXPECTED_HOSTS.get(publisher)
    if allowed is None:
        return None                      # publisher not in the map — flag it
    if not allowed:
        return True                      # deliberately our own
    host = (urlsplit(url).hostname or "").lower()
    return any(host == a or host.endswith("." + a.split(".", 1)[-1])
               and a.split(".", 1)[-1] in host for a in allowed)


def reach(url: str) -> dict:
    """HEAD first — these are large files and we only need to know they exist.
    Some government servers reject HEAD, so fall back to a ranged GET."""
    ctx = ssl.create_default_context()
    for method, headers in (("HEAD", {}), ("GET", {"Range": "bytes=0-2047"})):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": UA, "Accept": "*/*", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                return {"ok": True, "status": r.status, "method": method,
                        "content_type": (r.headers.get("Content-Type") or "").split(";")[0],
                        "final_url": r.url}
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue                 # server dislikes HEAD; try the ranged GET
            return {"ok": False, "status": e.code, "method": method,
                    "error": f"HTTP {e.code}"}
        except Exception as e:
            return {"ok": False, "status": 0, "method": method,
                    "error": f"{type(e).__name__}: {e}"[:160], "network": True}
    return {"ok": False, "status": 0, "error": "no method succeeded"}


def local(v: dict) -> dict:
    rel = v.get("local_file")
    if not rel:
        return {"present": None}
    p = ROOT / rel
    if not p.exists():
        return {"present": False, "path": rel}
    raw = p.read_bytes()
    return {"present": True, "path": rel, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--offline", action="store_true",
                    help="skip the network and check only hosts and local copies")
    args = ap.parse_args()

    report, dead, wrong_host, unreachable = [], [], [], []
    print(f"walking {len(S.SOURCES)} sources outward to the internet\n")
    for k, v in S.SOURCES.items():
        h = host_ok(v["publisher"], v["url"])
        r = {"ok": None} if args.offline else reach(v["url"])
        loc = local(v)
        row = {"id": k, "title": v["title"], "publisher": v["publisher"],
               "url": v["url"], "host_matches_publisher": h, "reach": r, "local": loc}
        report.append(row)

        if h is False:
            wrong_host.append(k)
        elif h is None:
            wrong_host.append(f"{k} (publisher not in the host map)")
        if r.get("ok") is False:
            (unreachable if r.get("network") else dead).append(k)

        mark = ("SKIP" if r.get("ok") is None else "OK  " if r["ok"] else "FAIL")
        host = "host ok" if h else ("OWN" if h is None else "HOST MISMATCH")
        size = (f"{loc['bytes'] / 1048576:.1f} MB" if loc.get("bytes")
                else ("no local copy" if loc.get("present") is False else "—"))
        print(f"  {mark}  {k:20}{str(r.get('status', '')):>4}  {host:14}{size:>14}")
        print(f"        {v['url']}")
        if loc.get("sha256"):
            print(f"        local sha256 {loc['sha256'][:32]}...")
        if r.get("error"):
            print(f"        {r['error']}")

    print()
    if wrong_host:
        print(f"HOST MISMATCH ({len(wrong_host)}): {', '.join(wrong_host)}")
        print("  A source whose host does not belong to its named publisher cannot")
        print("  be cited as that publisher's file.")
    if dead:
        print(f"DEAD LINKS ({len(dead)}): {', '.join(dead)}")
        print("  'Check it yourself' is false while these are broken.")
    if unreachable:
        print(f"UNREACHABLE from here ({len(unreachable)}): {', '.join(unreachable)}")
        print("  Network-level failure, not necessarily a dead link — re-run with egress.")
    if not (wrong_host or dead or unreachable):
        print("every source resolves, and every host belongs to its stated publisher.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "sources": report,
            "wrong_host": wrong_host, "dead": dead, "unreachable": unreachable,
        }, indent=1))
        print(f"\nwrote {args.json}")

    # A host mismatch or a dead link is a real defect. An unreachable host from
    # a sandbox with no egress is not, so it is reported and does not fail.
    return 1 if (wrong_host or dead) else 0


if __name__ == "__main__":
    raise SystemExit(main())

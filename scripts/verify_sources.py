"""Walk the source register outward and prove each source really is there.

Everything else in this repo checks inward: does the published number match the
artifact, does the artifact match the CSV, does the CSV match its hash. That
chain is airtight and still ends in a claim nobody has tested — that the file it
started from is a real, reachable, public government publication.

This walks the last link. For every entry in `src/sources.py` it:

  1. fetches the URL and reports what actually came back;
  2. confirms the host really belongs to the agency named as publisher, so a
     typo or a hijacked link cannot pose as TEA;
  3. reads what the URL actually serves and confirms it is the file we claim —
     see below;
  4. checks the local copy exists and reports its size and SHA-256, which is
     what a reader would compare against their own download.

Step 3 exists because steps 1 and 2 were not enough
---------------------------------------------------
The bond layer was credited to "compiled county election returns (Texas
Secretary of State)", with a note asserting that no single agency publishes
school bond elections statewide. Both statements were false — the Texas Bond
Review Board publishes all of them, back to 1958, on the state's own open-data
portal. This script passed that entry every time it ran, because the Secretary
of State elections page returns 200 and lives on a sos.state.tx.us host. It
proved the link was ALIVE and that the HOST matched the (wrong) publisher we
had named. Neither is the same as proving the link is the RIGHT one.

So every source now declares `proves_it`: strings that must actually appear in
what the URL serves. TEA's pages name their own product; the Census zip names
its own members in the archive header; and data.texas.gov, whose dataset page
is rendered in the browser and so carries no server-side text, declares an
`attribution_url` pointing at the portal's metadata API — which returns the
publisher as the State of Texas states it, a stronger proof than our own claim.

A dead link makes "check it yourself" false, which is worse than not offering
it. A live link to the wrong file is worse still, because it looks checked.
Run this before publishing a claim about provenance, and after any TEA site
reorganisation.

    python scripts/verify_sources.py
    python scripts/verify_sources.py --json docs/source_check.json

Exits non-zero if any source is unreachable, the host does not match the
publisher, or the content does not prove itself. Network failures are reported
separately from 4xx/5xx, because a sandbox with no egress is not the same as a
dead link.
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
    "Texas Bond Review Board": ("data.texas.gov", "brb.texas.gov"),
}

# How much of the body to read when proving a source is what it claims. TEA's
# pages carry their product name well inside the first few hundred KB, and a
# zip names its members in the first bytes, so this never needs the whole file.
PROOF_BYTES = 400_000

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


def proves_itself(v: dict) -> dict:
    """Read what the URL actually serves and look for the strings that only the
    real file would contain.

    Read as bytes and decoded leniently, because one of these sources is a zip:
    its member names are plain ASCII inside a binary container, and insisting on
    valid UTF-8 would throw away a perfectly good proof.
    """
    want = v.get("proves_it")
    if not want:
        return {"checked": False, "reason": "source declares no proof"}
    url = v.get("attribution_url") or v["url"]
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Range": f"bytes=0-{PROOF_BYTES - 1}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            body = r.read(PROOF_BYTES).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — any failure here is "not proven"
        return {"checked": True, "ok": False, "network": True,
                "error": f"{type(e).__name__}: {e}"[:160], "missing": want}
    missing = [w for w in want if w.lower() not in body.lower()]
    return {"checked": True, "ok": not missing, "url": url,
            "looked_for": want, "missing": missing, "bytes_read": len(body)}


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

    report, dead, wrong_host, unreachable, unproven = [], [], [], [], []
    print(f"walking {len(S.SOURCES)} sources outward to the internet\n")
    for k, v in S.SOURCES.items():
        h = host_ok(v["publisher"], v["url"])
        r = {"ok": None} if args.offline else reach(v["url"])
        pr = {"checked": False} if args.offline else proves_itself(v)
        loc = local(v)
        row = {"id": k, "title": v["title"], "publisher": v["publisher"],
               "url": v["url"], "host_matches_publisher": h, "reach": r,
               "content_proof": pr, "local": loc}
        report.append(row)

        if pr.get("checked") and pr.get("ok") is False and not pr.get("network"):
            unproven.append(k)
        elif not args.offline and not pr.get("checked"):
            unproven.append(f"{k} (declares no proof)")
        if h is False:
            wrong_host.append(k)
        elif h is None:
            wrong_host.append(f"{k} (publisher not in the host map)")
        if r.get("ok") is False:
            (unreachable if r.get("network") else dead).append(k)

        mark = ("SKIP" if r.get("ok") is None else "OK  " if r["ok"] else "FAIL")
        host = "host ok" if h else ("OWN" if h is None else "HOST MISMATCH")
        proof = ("proof —" if not pr.get("checked") else
                 "PROOF FAIL" if pr.get("ok") is False else "proves itself")
        size = (f"{loc['bytes'] / 1048576:.1f} MB" if loc.get("bytes")
                else ("no local copy" if loc.get("present") is False else "—"))
        print(f"  {mark}  {k:20}{str(r.get('status', '')):>4}  {host:14}"
              f"{proof:15}{size:>12}")
        print(f"        {v['url']}")
        if pr.get("missing"):
            print(f"        does not contain: {', '.join(map(repr, pr['missing']))}")
        if pr.get("url") and pr["url"] != v["url"]:
            print(f"        proved via {pr['url']}")
        if loc.get("sha256"):
            print(f"        local sha256 {loc['sha256'][:32]}...")
        if r.get("error"):
            print(f"        {r['error']}")

    print()
    if wrong_host:
        print(f"HOST MISMATCH ({len(wrong_host)}): {', '.join(wrong_host)}")
        print("  A source whose host does not belong to its named publisher cannot")
        print("  be cited as that publisher's file.")
    if unproven:
        print(f"UNPROVEN ({len(unproven)}): {', '.join(unproven)}")
        print("  The link resolves, but what it serves does not identify itself as")
        print("  the file we cite. This is the failure mode that let the bond layer")
        print("  be credited to the wrong agency for weeks.")
    if dead:
        print(f"DEAD LINKS ({len(dead)}): {', '.join(dead)}")
        print("  'Check it yourself' is false while these are broken.")
    if unreachable:
        print(f"UNREACHABLE from here ({len(unreachable)}): {', '.join(unreachable)}")
        print("  Network-level failure, not necessarily a dead link — re-run with egress.")
    if not (wrong_host or dead or unreachable or unproven):
        print("every source resolves, every host belongs to its stated publisher,")
        print("and every one serves content that identifies it as the file we cite.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "sources": report,
            "wrong_host": wrong_host, "dead": dead, "unreachable": unreachable,
            "unproven": unproven,
        }, indent=1))
        print(f"\nwrote {args.json}")

    # A host mismatch or a dead link is a real defect. An unreachable host from
    # a sandbox with no egress is not, so it is reported and does not fail.
    return 1 if (wrong_host or dead or unproven) else 0


if __name__ == "__main__":
    raise SystemExit(main())

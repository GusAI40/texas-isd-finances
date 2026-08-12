"""Does the publisher now have data this site has not ingested?

The failure this closes
-----------------------
Every other check here runs against what we HAVE: verify_sources.py proves the
publisher's file is the publisher's file, test_provenance.py re-derives every
headline from it, verify_artifacts.py rebuilds byte for byte, verify_live.py
compares production to the tree. All four passed, every run, for the weeks the
bond layer ran two years stale — because none of them can know that upstream
moved on. Staleness is invisible from inside the repo by construction.

So this runs the other way. `scripts/freshness_vintages.json` records the
vintage we KNOW we ingested for every source in `src/sources.py`; this script
asks each publisher what they have now, and exits non-zero for every source
whose upstream is newer than the recorded vintage. When it fires, either ingest
the release or bump the vintage with a note — both are edits to the JSON, and
the git diff is the record that the release was seen.

How each source is asked (the `method` field in the JSON):

    socrata       data.texas.gov's metadata API reports rowsUpdatedAt for the
                  dataset itself — the portal saying when its data last moved.
    page_year     TEA's download pages name their releases by year. Extract
                  the years with a source-specific pattern and compare the max.
                  Patterns must anchor on the release label, never a bare year:
                  every TEA page carries a 2026 copyright and nav links.
    next_url      year-pinned files (TIGER zips, the accountability workbook)
                  make the NEXT release's URL predictable. A 200 serving
                  non-HTML content means it shipped.
    etag          data.brb.texas.gov's issuer index has no updatedAt, but its
                  ETag is an S3 content hash: it moves only when the bytes move.
    unverifiable  an explicit admission the source offers no signal. Reported,
                  never failed — but every source must say so out loud, so a
                  silently unwatched source cannot exist.

A register source with no entry in the JSON fails the run outright: coverage
gaps are the whole disease.

Fetches go out with a named User-Agent. Bare urllib is answered with
Cloudflare's "error 1010" UA block on some state hosts — that is a bot filter,
not authentication, and identifying ourselves is the fix.

    python scripts/check_freshness.py
    python scripts/check_freshness.py --json docs/freshness.json

Exit 0: every verifiable source is at or behind our vintage. Exit 1: upstream
has something we have not ingested, or a source is uncovered. Network errors
are reported and do not fail — a sandbox without egress is not a stale site.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import sources as S  # noqa: E402

VINTAGE_FILE = Path(__file__).with_name("freshness_vintages.json")
UA = "txisd-freshness-check/1.0 (+https://txisd.dev/sources)"
TIMEOUT = 30
MAX_BODY = 800_000

# Result states, in the order they matter.
NEWER = "NEWER"            # upstream has data we have not ingested — fails
UNCOVERED = "UNCOVERED"    # register source with no vintage entry — fails
OK = "OK"                  # upstream is at or behind our vintage
UNVERIFIABLE = "UNVERIF"   # source offers no signal, or the signal vanished
ERROR = "ERROR"            # network-level failure — reported, not failed


def fetch(url: str, *, method: str = "GET", max_bytes: int = MAX_BODY,
          headers: dict | None = None) -> dict:
    """One HTTPS request, redirects followed, body capped at max_bytes.

    Always sends the named User-Agent — some state hosts sit behind a
    Cloudflare rule that 403s anonymous library clients ('error 1010')."""
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": UA, "Accept": "*/*", **(headers or {})})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            return {"status": r.status, "headers": dict(r.headers),
                    "body": r.read(max_bytes)}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "headers": dict(e.headers or {}), "body": b""}
    except Exception as e:  # noqa: BLE001 — DNS, TLS, timeout: all just "no answer"
        return {"status": 0, "headers": {}, "body": b"",
                "error": f"{type(e).__name__}: {e}"[:160]}


def _result(state: str, detail: str) -> dict:
    return {"state": state, "detail": detail}


def check_socrata(spec: dict, fetch_fn=fetch) -> dict:
    r = fetch_fn(spec["check_url"])
    if r.get("error"):
        return _result(ERROR, r["error"])
    if r["status"] != 200:
        return _result(ERROR, f"metadata API returned HTTP {r['status']}")
    try:
        meta = json.loads(r["body"])
    except ValueError:
        return _result(UNVERIFIABLE, "metadata API did not return JSON")
    stamps = [meta[k] for k in ("rowsUpdatedAt", "viewLastModified", "updatedAt")
              if isinstance(meta.get(k), (int, float))]
    if not stamps:
        return _result(UNVERIFIABLE, "metadata carries no update timestamp")
    upstream = datetime.fromtimestamp(max(stamps), tz=timezone.utc)
    ours = datetime.fromisoformat(spec["vintage_utc"].replace("Z", "+00:00"))
    stamp = upstream.strftime("%Y-%m-%d %H:%M UTC")
    if upstream > ours:
        return _result(NEWER, f"portal says data updated {stamp}; "
                              f"our vintage is {spec['vintage_utc']}")
    return _result(OK, f"last upstream update {stamp}, on or before our vintage")


def check_page_year(spec: dict, fetch_fn=fetch) -> dict:
    r = fetch_fn(spec["check_url"])
    if r.get("error"):
        return _result(ERROR, r["error"])
    if r["status"] != 200:
        return _result(ERROR, f"page returned HTTP {r['status']}")
    html = r["body"].decode("utf-8", "replace")
    years = [int(y) for m in re.finditer(spec["pattern"], html, re.IGNORECASE)
             for y in re.findall(r"20\d{2}", m.group(0))]
    if not years:
        return _result(UNVERIFIABLE,
                       "release-label pattern matched nothing — page redesigned? "
                       "The pattern in freshness_vintages.json needs re-anchoring.")
    latest, ours = max(years), spec["vintage_year"]
    if latest > ours:
        return _result(NEWER, f"page now advertises {latest}; we have {ours}")
    return _result(OK, f"latest advertised release is {latest}, which we have")


def check_next_url(spec: dict, fetch_fn=fetch) -> dict:
    r = fetch_fn(spec["check_url"], method="HEAD", max_bytes=0)
    if r["status"] in (403, 405, 501):     # server dislikes HEAD; ask for 2 KB
        r = fetch_fn(spec["check_url"], max_bytes=2048,
                     headers={"Range": "bytes=0-2047"})
    if r.get("error"):
        return _result(ERROR, r["error"])
    if r["status"] in (404, 410, 403):
        return _result(OK, f"next release ({spec['check_url'].rsplit('/', 1)[-1]}) "
                           "is not published yet")
    ctype = (r["headers"].get("Content-Type") or "").split(";")[0].strip()
    if r["status"] in (200, 206) and ctype and not ctype.startswith("text/html"):
        return _result(NEWER, f"next release exists upstream ({ctype}): "
                              f"{spec['check_url']}")
    if r["status"] in (200, 206):
        return _result(UNVERIFIABLE, "next-release URL answers 200 but serves "
                                     "HTML — likely a soft error page, check by hand")
    return _result(UNVERIFIABLE, f"unexpected HTTP {r['status']} probing next release")


def check_etag(spec: dict, fetch_fn=fetch) -> dict:
    r = fetch_fn(spec["check_url"], method="HEAD", max_bytes=0)
    if r["status"] in (403, 405, 501):
        r = fetch_fn(spec["check_url"], max_bytes=1024,
                     headers={"Range": "bytes=0-1023"})
    if r.get("error"):
        return _result(ERROR, r["error"])
    if r["status"] not in (200, 206):
        return _result(ERROR, f"file returned HTTP {r['status']}")

    def clean(tag: str | None) -> str:
        return (tag or "").removeprefix("W/").strip('" ')

    etag, ours = clean(r["headers"].get("ETag")), clean(spec.get("etag"))
    if etag and ours:
        if etag != ours:
            return _result(NEWER, f"file changed upstream: ETag {etag!r} vs "
                                  f"recorded {ours!r}")
        return _result(OK, "ETag unchanged since our ingest")
    lastmod, ours_lm = r["headers"].get("Last-Modified"), spec.get("last_modified")
    if lastmod and ours_lm:
        if lastmod != ours_lm:
            return _result(NEWER, f"Last-Modified moved: {lastmod!r} vs "
                                  f"recorded {ours_lm!r}")
        return _result(OK, "Last-Modified unchanged since our ingest")
    return _result(UNVERIFIABLE, "server offers neither ETag nor Last-Modified")


def check_unverifiable(spec: dict, fetch_fn=fetch) -> dict:
    return _result(UNVERIFIABLE, spec.get("meaning", "source offers no signal"))


CHECKERS = {
    "socrata": check_socrata,
    "page_year": check_page_year,
    "next_url": check_next_url,
    "etag": check_etag,
    "unverifiable": check_unverifiable,
}


def load_vintages(path: Path = VINTAGE_FILE) -> dict:
    return json.loads(path.read_text())


def evaluate(register: dict, vintages: dict, fetch_fn=fetch) -> list[dict]:
    """One row per register source, in register order. Pure enough to test:
    pass a fake fetch_fn and a fake register/vintage record."""
    rows = []
    specs = vintages["sources"]
    for source_id in register:
        spec = specs.get(source_id)
        if spec is None:
            rows.append({"id": source_id, "method": "—", **_result(
                UNCOVERED, "in src/sources.py but has no vintage entry — "
                           "an unwatched source is the exact hole this closes")})
            continue
        checker = CHECKERS.get(spec.get("method", ""))
        if checker is None:
            rows.append({"id": source_id, "method": spec.get("method", "?"),
                         **_result(UNCOVERED, f"unknown method {spec.get('method')!r}")})
            continue
        rows.append({"id": source_id, "method": spec["method"],
                     **checker(spec, fetch_fn)})
    for extra in set(specs) - set(register):
        rows.append({"id": extra, "method": specs[extra].get("method", "?"),
                     **_result(UNVERIFIABLE,
                               "vintage entry for a source no longer in the "
                               "register — delete it")})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, default=None,
                    help="also write the full report as JSON")
    args = ap.parse_args(argv)

    vintages = load_vintages()
    print(f"asking {len(S.SOURCES)} publishers whether they have moved past "
          f"our recorded vintages ({vintages.get('recorded', '?')})\n")
    rows = evaluate(S.SOURCES, vintages)

    for row in rows:
        print(f"  {row['state']:8} {row['id']:22} [{row['method']}]")
        print(f"           {row['detail']}")

    newer = [r["id"] for r in rows if r["state"] == NEWER]
    uncovered = [r["id"] for r in rows if r["state"] == UNCOVERED]
    errors = [r["id"] for r in rows if r["state"] == ERROR]

    print()
    if newer:
        print(f"UPSTREAM IS NEWER ({len(newer)}): {', '.join(newer)}")
        print("  The publisher has data this site has not ingested. Ingest it, or")
        print("  bump the vintage in scripts/freshness_vintages.json with a note —")
        print("  the diff is the record that the release was seen.")
    if uncovered:
        print(f"UNCOVERED ({len(uncovered)}): {', '.join(uncovered)}")
        print("  Every source must be watched or explicitly declared unverifiable.")
    if errors:
        print(f"UNREACHABLE from here ({len(errors)}): {', '.join(errors)}")
        print("  Network failure, not staleness — re-run somewhere with egress.")
    if not (newer or uncovered or errors):
        print("every verifiable source is at or behind our recorded vintage.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"recorded": vintages.get("recorded"), "results": rows,
             "newer": newer, "uncovered": uncovered, "errors": errors}, indent=1))
        print(f"\nwrote {args.json}")

    return 1 if (newer or uncovered) else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Check what production actually serves against what this repo says it should.

The hole this closes
--------------------
Three checks already guard the numbers, and all three run inward from the
deployed site:

    verify_sources.py     the publisher's file really is the publisher's file
    test_provenance.py    every headline re-derives from that file, longhand
    verify_artifacts.py   the committed artefact is what the builder produces

A repo can pass all three and still be irrelevant, because none of them has any
idea what is on the internet. That is not hypothetical: the bond layer ran for
weeks two years stale, 404 propositions short, publicly naming districts as
having no voter-approved bond after they had passed one — with a green suite
the whole time. The tests were checking the repo. Nobody was checking the site.

So this runs the other way. It fetches the live endpoints and compares the
figures a reader actually sees against the artefacts this working tree would
deploy. Any difference is one of exactly two things, and both matter:

    STALE     production is behind the repo — a deploy is owed
    UNKNOWN   production has something the repo does not — someone deployed
              from a different tree, which is worse, because the running site
              cannot be reproduced from source

It deliberately compares HEADLINE figures rather than whole payloads. A byte
diff would fire on every rounding change and be switched off within a month;
these are the specific numbers that appear on a page, get quoted, and would
embarrass us if they were wrong.

    python scripts/verify_live.py
    python scripts/verify_live.py --base http://127.0.0.1:8000
    python scripts/verify_live.py --json docs/live_check.json

Exits non-zero on any drift, so it can run as a cron or a deploy gate. A
network failure is reported separately and does NOT fail the run — an agent
sandbox with no egress is not a broken deployment.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

BASE = "https://txisd.dev"
UA = "txisd-live-check/1.0 (+https://txisd.dev/sources)"
TIMEOUT = 45


def dig(obj: Any, path: str) -> Any:
    """`a.b.0.c` -> obj["a"]["b"][0]["c"], or None anywhere it runs out."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


# Every check is (label, live endpoint, path into the live body, artefact file,
# path into the artefact). Where the endpoint flattens a payload the two paths
# differ — that asymmetry is the point of writing them out rather than deriving
# them, because it is what a reader's URL actually returns.
CHECKS: list[tuple[str, str, str, str, str]] = [
    # --- bonds: the layer that was silently stale for weeks ------------------
    ("bond propositions", "/bonds/texas", "meta.propositions",
     "bond_data.json", "meta.propositions"),
    ("bond districts", "/bonds/texas", "meta.districts_with_history",
     "bond_data.json", "meta.districts_with_history"),
    ("most recent bond year", "/bonds/texas", "meta.last_year",
     "bond_data.json", "meta.last_year"),
    ("total ever asked at the ballot", "/bonds/texas", "meta.total_asked",
     "bond_data.json", "meta.total_asked"),
    # --- debt outstanding ----------------------------------------------------
    ("debt still owed", "/debt/texas", "total", "debt_data.json", "texas.total"),
    ("interest not yet paid", "/debt/texas", "interest", "debt_data.json",
     "texas.interest"),
    ("year the debt clears", "/debt/texas", "clears_in", "debt_data.json",
     "texas.clears_in"),
    ("districts carrying CABs", "/debt/texas", "cab.districts", "debt_data.json",
     "texas.cab.districts"),
    # --- the seventeen-year trend -------------------------------------------
    ("districts with a trend", "/trends/texas", "meta.districts",
     "trend_data.json", "meta.districts"),
    ("trend last year", "/trends/texas", "meta.last_year",
     "trend_data.json", "meta.last_year"),
    # --- the forensic file ---------------------------------------------------
    ("districts in the forensic file", "/forensics/texas", "statewide.districts",
     "forensic_data.json", "statewide.districts"),
    ("statewide debt service", "/forensics/texas", "statewide.debt_total",
     "forensic_data.json", "statewide.debt_total"),
    ("recapture payers", "/forensics/texas", "statewide.recapture_payers",
     "forensic_data.json", "statewide.recapture_payers"),
    ("propositions in the ballot record", "/forensics/texas", "statewide.ballot.propositions",
     "forensic_data.json", "statewide.ballot.propositions"),
    # --- campuses: the only layer that names individual schools -------------
    ("students in a D/F campus inside an A/B district", "/campuses/texas",
     "hidden_by_the_district_average.students", "campus_data.json",
     "texas.hidden_by_the_district_average.students"),
    ("campuses hidden by the district average", "/campuses/texas",
     "hidden_by_the_district_average.campuses", "campus_data.json",
     "texas.hidden_by_the_district_average.campuses"),
    ("districts whose campuses differ", "/campuses/texas", "spread.campuses_differ",
     "campus_data.json", "texas.spread.campuses_differ"),
    # --- the forensic quality layer, incl. the list that named districts -----
    ("districts with debt and no approved bond", "/forensics/quality",
     "debt_without_a_ballot.no_voter_approved_bond_on_record.districts",
     "forensic_quality.json",
     "debt_without_a_ballot.no_voter_approved_bond_on_record.districts"),
    ("figures tested by Benford", "/forensics/quality", "benford.figures_tested",
     "forensic_quality.json", "benford.figures_tested"),
]

# Claims that are not numbers. A wrong publisher is exactly as damaging as a
# wrong figure and nothing else on this site would catch it, because the
# citation renders as prose.
TEXT_CHECKS: list[tuple[str, str, Callable[[Any], Any], str]] = [
    ("bond publisher named on /sources", "/sources",
     lambda body: "Texas Bond Review Board" in body,
     "the live site must credit the Bond Review Board for bond elections"),
    ("the retired Secretary of State citation is gone", "/sources",
     lambda body: "sos.state.tx.us" not in body,
     "the corrected citation must not still be live"),
]

_ctx = ssl.create_default_context()


def get(url: str) -> tuple[Any, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # The site answered. A 404 here means the endpoint is not deployed —
        # that is a finding, not a transport problem, and conflating the two
        # would let a missing layer hide behind "no egress from the sandbox".
        return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — transport failure, reported not fatal
        return None, f"TRANSPORT {type(e).__name__}: {e}"[:120]
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return raw, None


def post(url: str, payload: dict) -> tuple[Any, str | None]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "User-Agent": UA, "Accept": "application/json",
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90, context=_ctx) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"TRANSPORT {type(e).__name__}: {e}"[:120]
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return raw, None


def check_query(base: str) -> tuple[bool, str]:
    """Ask the live agent the one question with a known, checkable answer.

    /query was the only reader-facing feature nothing verified in production.
    It is also the feature with a REGRESSION ON RECORD: the prompt once said
    "default LIMIT 100", so the agent LIMITed a SELECT DISTINCT and answered
    "100 districts" instead of 1,310 — intermittently, which is the worst kind.
    So the check is that exact question, and it fails on the exact wrong answer
    as well as on a missing right one.

    Costs one LLM call, so it is opt-in (--with-query) rather than part of the
    free deploy gate.
    """
    want = 1310
    body, err = post(base + "/query", {"question":
                                       "How many school districts are in the data?"})
    if err:
        return False, f"/query did not answer: {err}"
    if not isinstance(body, dict):
        return False, "/query returned a non-JSON body"
    answer = " ".join(str(body.get(k, "")) for k in ("answer", "sql", "result"))
    digits = re.sub(r"[,\s]", "", answer)
    if str(want) in digits:
        return True, f"agent still answers {want:,}"
    if re.search(r"\b100\b", answer):
        return False, ("agent answered 100 — the LIMIT-on-a-COUNT regression is "
                       "back; see the 'counting is not limiting' rule")
    return False, f"agent did not answer {want:,}: {answer[:160]!r}"


def same(a: Any, b: Any) -> bool:
    """Equal enough. Floats are compared relatively because a payload that
    round-trips through JSON can differ in the last bit without anything having
    changed; anything a reader would notice is far larger than this."""
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == b:
            return True
        scale = max(abs(a), abs(b), 1)
        return abs(a - b) / scale < 1e-9
    return a == b


def load_artifacts() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in {c[3] for c in CHECKS}:
        p = STATIC / name
        out[name] = json.loads(p.read_text()) if p.exists() else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=BASE, help="site to check (default: production)")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--with-query", action="store_true",
                    help="also ask the live NLP agent one question with a "
                         "known answer. Costs one LLM call, so it is opt-in.")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    arts = load_artifacts()
    bodies: dict[str, Any] = {}
    rows, drift, missing, unreachable = [], [], [], []

    print(f"checking {base} against this working tree\n")

    for label, ep, live_path, art_name, art_path in CHECKS:
        if ep not in bodies:
            bodies[ep] = get(base + ep)
        body, err = bodies[ep]
        art = arts.get(art_name)
        expect = dig(art, art_path) if art else None
        actual = dig(body, live_path) if body is not None else None

        if err and err.startswith("TRANSPORT"):
            state = "UNREACHABLE"
            unreachable.append(f"{ep} ({err})")
        elif err:
            state = "MISSING LIVE"           # the site answered, and said no
            missing.append(f"{label} ({ep} -> {err})")
        elif art is None:
            state = "NO ARTIFACT"
        elif actual is None:
            # The endpoint answered but has no such field: the live build
            # predates this layer entirely.
            state = "MISSING LIVE"
            missing.append(label)
        elif same(actual, expect):
            state = "ok"
        else:
            state = "DRIFT"
            drift.append((label, expect, actual))

        rows.append({"check": label, "endpoint": ep, "expected": expect,
                     "live": actual, "state": state, "error": err})
        mark = {"ok": "  ok  ", "DRIFT": " DRIFT", "MISSING LIVE": " ABSENT",
                "UNREACHABLE": " ---- ", "NO ARTIFACT": " ---- "}[state]
        shown = "" if state in ("UNREACHABLE", "NO ARTIFACT") else (
            f"  repo {expect!r}" + (f"   live {actual!r}" if state != "ok" else ""))
        print(f"{mark}  {label:44}{shown}")

    for label, ep, ok, why in TEXT_CHECKS:
        if ep not in bodies:
            bodies[ep] = get(base + ep)
        body, err = bodies[ep]
        text = body if isinstance(body, str) else json.dumps(body or "")
        if err and err.startswith("TRANSPORT"):
            state, unreachable = "UNREACHABLE", unreachable + [f"{ep} ({err})"]
        elif err:
            state = "MISSING LIVE"
            missing.append(f"{label} ({ep} -> {err})")
        elif ok(text):
            state = "ok"
        else:
            state = "DRIFT"
            drift.append((label, why, "not true of the live site"))
        rows.append({"check": label, "endpoint": ep, "state": state, "error": err})
        print(f"{'  ok  ' if state == 'ok' else ' DRIFT' if state == 'DRIFT' else ' ---- '}"
              f"  {label:44}")

    if args.with_query:
        good, why = check_query(base)
        rows.append({"check": "live NLP agent answers correctly",
                     "endpoint": "/query", "state": "ok" if good else "DRIFT",
                     "error": None if good else why})
        print(f"{'  ok  ' if good else ' DRIFT'}  "
              f"{'live NLP agent answers correctly':44}{'' if good else '  ' + why}")
        if not good:
            drift.append(("live NLP agent", "a checkable answer", why))

    print()
    if missing:
        print(f"NOT DEPLOYED ({len(missing)}): {', '.join(missing)}")
        print("  The live build predates these layers. A deploy is owed.")
    if drift:
        print(f"DRIFT ({len(drift)}):")
        for label, expect, actual in drift:
            print(f"  {label}: repo says {expect!r}, the site serves {actual!r}")
        print("  Either production is behind this tree, or it was deployed from a")
        print("  different one. The second is worse: the running site cannot then")
        print("  be reproduced from source.")
    if unreachable:
        print(f"UNREACHABLE ({len(set(unreachable))}): {', '.join(sorted(set(unreachable)))}")
        print("  Network-level failure, not necessarily a broken site.")
    if not (drift or missing or unreachable):
        print("the live site serves exactly what this tree would deploy.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"base": base, "checks": rows,
             "drift": [d[0] for d in drift], "not_deployed": missing,
             "unreachable": sorted(set(unreachable))}, indent=1))
        print(f"\nwrote {args.json}")

    return 1 if (drift or missing) else 0


if __name__ == "__main__":
    sys.exit(main())

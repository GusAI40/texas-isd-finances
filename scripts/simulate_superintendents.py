"""Monte Carlo: 1,000 superintendents use this system, and we find where it breaks.

The bug classes this is built to find
-------------------------------------
The test suite proves the code is correct. It cannot prove the PRODUCT works,
because the failures that matter to a superintendent are not exceptions:

1. **DEAD END** — the page or endpoint answers 200 and has nothing to say.
   259 current districts have no bond election on record, so the bond section
   is empty for them. That is correct behaviour and a bad experience, and no
   status code will ever tell you it happened.
2. **SILENT BLANK** — a field the page renders is null for this district.
   Charters levy no property tax, so "your tax bill" is blank for every one of
   them.
3. **COVERAGE CLIFF** — a district present in one layer and missing from
   another, so a journey that crosses layers fails halfway.
4. **SLOW** — a payload big enough to hurt on the phone a trustee is holding.
5. **HTTP FAULT** — the ordinary kind. Rarest, and the least interesting.

Method
------
Personas are drawn from the REAL district population, weighted by enrolment so
the simulation spends its attention where the students are. Each superintendent
runs a multi-step journey with a motive, and every step is a real request
against a real deployment. Failures are then ranked by **students affected**,
not by count, because 259 tiny districts and one Houston are not the same
problem.

Seeded, so a fix can be measured against the same population.

    python scripts/simulate_superintendents.py --base https://txisd.dev
    python scripts/simulate_superintendents.py --base http://127.0.0.1:8802 -n 200
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SEED = 20260810
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

# Who actually opens this. Weights are modelled, not measured; the district
# population underneath them is real.
PERSONAS = {
    # motive                      weight  journey
    "budget_season": 0.28,        # building next year's budget, wants peers
    "board_prep": 0.22,           # a trustee asked a question before a meeting
    "bond_planning": 0.16,        # considering going to the voters
    "press_inquiry": 0.12,        # a reporter called about the deficit story
    "benchmarking": 0.12,         # how do we compare, honestly
    "recruitment": 0.10,          # explaining the district to a candidate
}

# Each journey is the sequence of requests that motive actually produces.
# `{d}` is the district number.
JOURNEYS: dict[str, list[tuple[str, str]]] = {
    "budget_season": [
        ("portal", "/"),
        ("my finances", "/district/{d}/summary"),
        ("what it buys", "/district/{d}/outcomes"),
        ("peers", "/district/{d}/peers"),
        ("breakdown", "/district/{d}/breakdown"),
        ("economics", "/district/{d}/economics"),
    ],
    "board_prep": [
        ("portal", "/"),
        ("my finances", "/district/{d}/summary"),
        ("forensic file", "/district/{d}/forensics"),
        ("trajectory", "/district/{d}/trends"),
        ("statewide context", "/trends/texas"),
    ],
    "bond_planning": [
        ("bond history", "/district/{d}/bonds"),
        ("statewide bonds", "/bonds/texas"),
        ("debt load", "/district/{d}/forensics"),
        ("economics", "/district/{d}/economics"),
    ],
    "press_inquiry": [
        ("forensic page", "/forensics"),
        ("statewide forensics", "/forensics/texas"),
        ("my file", "/district/{d}/forensics"),
        ("my trajectory", "/district/{d}/trends"),
        ("the feed", "/briefing"),
    ],
    "benchmarking": [
        ("my finances", "/district/{d}/summary"),
        ("peers", "/district/{d}/peers"),
        ("insights", "/district/{d}/insights"),
        ("equity", "/district/{d}/equity"),
        ("turnarounds", "/district/{d}/turnarounds"),
    ],
    "recruitment": [
        ("portal", "/"),
        ("my outcomes", "/district/{d}/outcomes"),
        ("map", "/geomap"),
        ("boundaries", "/district-geo"),
        ("equity", "/district/{d}/equity"),
    ],
}

# A step that answers 200 but has nothing in it. Checked per endpoint, because
# "empty" means something different for each.
def emptiness(path_kind: str, body) -> str | None:
    """Return a DEAD END reason, or None if the answer had content.

    An explained absence is content. "None of the 14 districts most like you
    reversed a sustained deficit in seventeen years" is an answer — a better
    one than a list would have been. Only silence is a dead end.
    """
    if body is None:
        return None
    if isinstance(body, dict):
        if body.get("absence") or body.get("absences"):
            return None
    try:
        if path_kind == "bonds":
            return None if (body.get("elections") or []) else "no bond election on record"
        if path_kind == "trends":
            return None if (body.get("series") or {}).get("instruction_share") else "no trend series"
        if path_kind == "forensics":
            missing = [k for k in ("outside_operating", "who_pays", "where_it_landed")
                       if not body.get(k)]
            return f"missing {', '.join(missing)}" if missing else None
        if path_kind == "economics":
            if not (body.get("tax") or {}).get("bill_on_home"):
                return "no tax figure (charter, or tax base estimates disagreed)"
            return None
        if path_kind == "peers":
            peers = body.get("peers") if isinstance(body, dict) else body
            return None if peers else "no structural peers found"
        if path_kind == "equity":
            return None if body else "no equity record"
        if path_kind == "summary":
            return None if body else "no finance history"
        if path_kind == "outcomes":
            return None if (body.get("measures") or {}) else "no outcome measures"
        if path_kind == "insights":
            items = body.get("insights") if isinstance(body, dict) else body
            return None if items else "no insights generated"
        if path_kind == "turnarounds":
            items = body.get("turnarounds") if isinstance(body, dict) else body
            return None if items else "no turnaround found among peers"
    except Exception:
        return None
    return None


def kind_of(path: str) -> str:
    for k in ("forensics", "trends", "bonds", "economics", "equity", "outcomes",
              "peers", "insights", "turnarounds", "summary", "breakdown"):
        if path.endswith("/" + k):
            return k
    return "page"


def fetch(base: str, path: str, timeout: float) -> dict:
    url = base.rstrip("/") + path
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={
        "User-Agent": "txisd-superintendent-sim/1.0", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ms = (time.perf_counter() - t0) * 1000
            body = None
            if "json" in (r.headers.get("Content-Type") or ""):
                try:
                    body = json.loads(raw)
                except Exception:
                    body = None
            return {"status": r.status, "ms": ms, "bytes": len(raw), "body": body}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "ms": (time.perf_counter() - t0) * 1000,
                "bytes": 0, "body": None}
    except Exception as e:
        return {"status": 0, "ms": (time.perf_counter() - t0) * 1000, "bytes": 0,
                "body": None, "err": type(e).__name__}


def population() -> list[dict]:
    """Every district a superintendent could actually be running, with the
    enrolment that decides how much a failure there costs."""
    data = json.loads((STATIC / "forensic_data.json").read_text())
    rows = [{"num": r["n"], "name": r["name"], "students": r["students"] or 0}
            for r in data["table"]]
    return [r for r in rows if r["students"] > 0]


def run(base: str, n: int, workers: int, timeout: float, seed: int) -> dict:
    rng = random.Random(seed)
    pop = population()
    # Weight by enrolment: a superintendent is a person, and there are more
    # people behind Houston than behind a 200-student district. Sampling
    # uniformly would spend 90% of the run on districts almost nobody attends.
    weights = [r["students"] for r in pop]
    motives = list(PERSONAS)
    mweights = [PERSONAS[m] for m in motives]

    supers = []
    for i in range(n):
        d = rng.choices(pop, weights=weights, k=1)[0]
        supers.append({"id": i, "district": d,
                       "motive": rng.choices(motives, weights=mweights, k=1)[0]})

    steps: list[dict] = []

    def one(sup: dict) -> list[dict]:
        out = []
        for label, tpl in JOURNEYS[sup["motive"]]:
            path = tpl.format(d=sup["district"]["num"])
            res = fetch(base, path, timeout)
            kind = kind_of(path)
            dead = emptiness(kind, res["body"]) if res["status"] == 200 else None
            out.append({
                "super": sup["id"], "motive": sup["motive"],
                "district": sup["district"]["num"], "name": sup["district"]["name"],
                "students": sup["district"]["students"],
                "label": label, "path": path, "kind": kind,
                "status": res["status"], "ms": res["ms"], "bytes": res["bytes"],
                "dead_end": dead,
            })
        return out

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for batch in ex.map(one, supers):
            steps.extend(batch)
    wall = time.perf_counter() - t0
    return {"steps": steps, "supers": supers, "wall_s": wall, "base": base,
            "n": n, "seed": seed}


def report(res: dict) -> dict:
    steps = res["steps"]
    n = res["n"]
    by_step = defaultdict(list)
    for s in steps:
        by_step[(s["label"], s["path"].replace(s["district"], "{d}"))].append(s)

    # --- fault lines, ranked by students behind them ------------------------
    faults = []
    for (label, path), rows in by_step.items():
        http_bad = [r for r in rows if r["status"] >= 400 or r["status"] == 0]
        dead = [r for r in rows if r["dead_end"]]
        lat = sorted(r["ms"] for r in rows)
        affected = {r["district"] for r in dead} | {r["district"] for r in http_bad}
        students = sum({r["district"]: r["students"] for r in dead + http_bad}.values())
        if http_bad or dead:
            faults.append({
                "step": label, "path": path, "requests": len(rows),
                "http_errors": len(http_bad),
                "dead_ends": len(dead),
                "dead_end_rate": round(len(dead) / len(rows) * 100, 1),
                "districts_affected": len(affected),
                "students_affected": students,
                "reasons": Counter(r["dead_end"] for r in dead).most_common(3),
                "p50_ms": round(statistics.median(lat)),
                "p95_ms": round(lat[int(len(lat) * 0.95)]) if lat else 0,
            })
    faults.sort(key=lambda f: -f["students_affected"])

    # --- did a whole journey fail? ------------------------------------------
    per_super = defaultdict(list)
    for s in steps:
        per_super[s["super"]].append(s)
    broken_journeys = Counter()
    dead_end_journeys = Counter()
    clean = 0
    clean_of_dead_ends = 0
    for sid, rows in per_super.items():
        http_bad = [r for r in rows if r["status"] >= 400 or r["status"] == 0]
        dead = [r for r in rows if r["dead_end"]]
        if http_bad or dead:
            broken_journeys[rows[0]["motive"]] += 1
        else:
            clean += 1
        # The product metric. An http fault here is usually the network path
        # this simulation runs through, not the app — mixing the two makes a
        # real product improvement invisible behind transport noise.
        if dead:
            dead_end_journeys[rows[0]["motive"]] += 1
        else:
            clean_of_dead_ends += 1

    lat_all = sorted(s["ms"] for s in steps)
    slow = sorted(by_step.items(),
                  key=lambda kv: -statistics.median(r["ms"] for r in kv[1]))[:6]
    heavy = sorted(by_step.items(),
                   key=lambda kv: -statistics.median(r["bytes"] for r in kv[1]))[:6]

    return {
        "base": res["base"], "superintendents": n, "requests": len(steps),
        "wall_s": round(res["wall_s"], 1),
        "clean_journeys": clean,
        "clean_journey_pct": round(clean / n * 100, 1),
        "clean_of_dead_ends": clean_of_dead_ends,
        "clean_of_dead_ends_pct": round(clean_of_dead_ends / n * 100, 1),
        "dead_end_journeys_by_motive": {
            m: {"with_dead_end": dead_end_journeys[m],
                "of": sum(1 for s2 in res["supers"] if s2["motive"] == m)}
            for m in PERSONAS},
        "broken_by_motive": {m: {"broken": broken_journeys[m],
                                 "of": sum(1 for s in res["supers"] if s["motive"] == m)}
                             for m in PERSONAS},
        "latency_ms": {"p50": round(statistics.median(lat_all)),
                       "p95": round(lat_all[int(len(lat_all) * 0.95)]),
                       "p99": round(lat_all[int(len(lat_all) * 0.99)]),
                       "max": round(lat_all[-1])},
        "fault_lines": faults,
        "slowest": [{"step": k[0], "path": k[1],
                     "p50_ms": round(statistics.median(r["ms"] for r in v))}
                    for k, v in slow],
        "heaviest": [{"step": k[0], "path": k[1],
                      "median_kb": round(statistics.median(r["bytes"] for r in v) / 1024, 1)}
                     for k, v in heavy],
        "http_status_counts": dict(Counter(s["status"] for s in steps)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="https://txisd.dev")
    ap.add_argument("-n", type=int, default=1000, help="superintendents")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent superintendents; keep modest, this is real traffic")
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=Path("docs/superintendent_sim.json"))
    args = ap.parse_args()

    if not (STATIC / "forensic_data.json").exists():
        print("run scripts/build_forensic_data.py first", file=sys.stderr)
        return 1

    print(f"{args.n:,} superintendents against {args.base}, "
          f"{args.workers} at a time...", flush=True)
    res = run(args.base, args.n, args.workers, args.timeout, args.seed)
    rep = report(res)

    print(f"\n{rep['requests']:,} requests in {rep['wall_s']}s")
    print(f"journeys with NO DEAD END (the product metric): "
          f"{rep['clean_of_dead_ends']:,}/{rep['superintendents']:,} "
          f"({rep['clean_of_dead_ends_pct']}%)")
    print(f"journeys with no fault of any kind, transport included: "
          f"{rep['clean_journeys']:,}/{rep['superintendents']:,} "
          f"({rep['clean_journey_pct']}%)")
    L = rep["latency_ms"]
    print(f"latency p50 {L['p50']}ms  p95 {L['p95']}ms  p99 {L['p99']}ms  max {L['max']}ms")
    print(f"status codes: {rep['http_status_counts']}")

    print("\nFAULT LINES, ranked by students behind them")
    print(f"{'step':22}{'dead':>6}{'http':>6}{'rate':>7}{'districts':>10}{'students':>11}  reason")
    for f in rep["fault_lines"]:
        reason = f["reasons"][0][0] if f["reasons"] else "http error"
        print(f"{f['step'][:21]:22}{f['dead_ends']:>6}{f['http_errors']:>6}"
              f"{f['dead_end_rate']:>6.1f}%{f['districts_affected']:>10,}"
              f"{f['students_affected']:>11,}  {str(reason)[:44]}")

    print("\nBROKEN JOURNEYS BY MOTIVE")
    for m, v in rep["broken_by_motive"].items():
        pct = v["broken"] / v["of"] * 100 if v["of"] else 0
        print(f"  {m:16}{v['broken']:>5}/{v['of']:<5} {pct:5.1f}%")

    print("\nSLOWEST STEPS")
    for s in rep["slowest"]:
        print(f"  {s['step'][:22]:24}{s['p50_ms']:>6}ms  {s['path']}")
    print("\nHEAVIEST PAYLOADS (uncompressed at the client)")
    for s in rep["heaviest"]:
        print(f"  {s['step'][:22]:24}{s['median_kb']:>7} KB  {s['path']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

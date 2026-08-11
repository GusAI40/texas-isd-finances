"""100,000 visitors a month: what they cost, and what gives way first.

Why this is a model and not a load test
---------------------------------------
Firing 100,000 requests at production would be abusive, and from this sandbox it
would measure the agent proxy rather than the site — an earlier run produced
30-second timeouts at concurrency 1. So the arrivals are modelled, a
representative sample of journeys is measured for real against a local build,
and the month is extrapolated from what those journeys actually cost.

The thing that breaks is never the mean
---------------------------------------
100,000 a month is 3,300 a day, which is nothing. A transparency site does not
receive traffic that way. It receives nothing for three weeks and then a
reporter links to it, and a third of the month arrives in six hours. So arrivals
are drawn overdispersed — a small number of spike days carrying a large share of
the month — and the report is about the worst hour, not the average one.

What is actually being measured
-------------------------------
Per journey: requests, bytes served, how many of those requests need the
database, and how many reach the language model. Those four are the whole cost
model, because:

- Vercel bills invocations and bandwidth;
- Supabase free tier PAUSES after ~7 days idle and has a connection ceiling —
  and 16 of this site's 54 routes touch it;
- DeepSeek bills per call, and `/query` is the only unbounded-cost path here.

Every other endpoint is committed JSON and survives a dead database, which the
model reports as a resilience number rather than assuming.

    python scripts/simulate_visitors.py --base http://127.0.0.1:8000
    python scripts/simulate_visitors.py --visitors 1000000 --sample 400

Seeded, so two runs of the same month are the same month.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260811
VISITORS = 100_000

# How a visitor arrives, and therefore what they do. Weights are a judgement
# about a Texas school-finance site, not a measurement — stated here rather than
# buried so they can be argued with.
ARRIVALS = {
    "search for their own district": 0.42,   # the overwhelming default
    "shared link to one district": 0.18,     # someone posted a district page
    "news story about a finding": 0.14,      # a reporter linked the statewide page
    "browsing the map": 0.10,
    "an assistant using the MCP tools": 0.08,
    "researcher or reporter digging": 0.05,
    "checking the sources": 0.03,
}

# What each arrival does, as endpoint templates. {d} is a district number.
JOURNEYS = {
    "search for their own district": [
        "/", "/fallback-index", "/district/{d}/summary", "/district/{d}/economics",
        "/district/{d}/outcomes", "/district/{d}/campuses"],
    "shared link to one district": [
        "/", "/district/{d}/summary", "/district/{d}/forensics",
        "/district/{d}/bonds", "/district/{d}/debt"],
    "news story about a finding": [
        "/forensics", "/forensics/texas", "/trends/texas", "/debt/texas",
        "/campuses/texas", "/bonds/texas"],
    "browsing the map": ["/geomap", "/district-geo", "/district/{d}/summary"],
    "an assistant using the MCP tools": ["MCP:server/discover", "MCP:tools/list",
                                         "MCP:district_money", "MCP:district_debt"],
    "researcher or reporter digging": [
        "/forensics", "/forensics/quality", "/provenance", "/sources",
        "/trends/texas", "/district/{d}/trends", "/district/{d}/campuses",
        "/districts?limit=50"],
    "checking the sources": ["/sources", "/provenance", "/health"],
}

# The share of visitors who ask the natural-language question. This is the only
# per-visit cost that is not fixed, and the only one that can produce a bill.
QUERY_RATE = 0.015
DEEPSEEK_PER_CALL_USD = 0.0009      # ~6s call, deepseek-v4-flash, in+out

# A month's arrivals are not uniform. `SPIKE_DAYS` days carry `SPIKE_SHARE` of
# the traffic, and within a spike day it lands in roughly six hours.
SPIKE_DAYS, SPIKE_SHARE, SPIKE_HOURS = 3, 0.45, 6

# Concurrency cannot be estimated from LOCAL latency. A loopback request to
# uvicorn answers in ~15ms; the same request on Vercel, through a cold start and
# a pooled connection to Supabase in another region, answered at p50 295ms and
# p95 1.0s when 1,000 simulated superintendents ran against production
# (docs/superintendent_sim.json). That measurement is the input here, and it is
# an INPUT rather than something this script measured — using the local figure
# would divide the concurrency estimate by twenty and report that nothing ever
# breaks.
PROD_P50_SECONDS = 0.295
PROD_P95_SECONDS = 1.003

# Vercel Hobby/Pro limits worth measuring against.
VERCEL_FUNCTION_MAX_CONCURRENCY = 1000
SUPABASE_POOLER_CONNECTIONS = 200


def get(base: str, path: str, timeout: float = 30) -> tuple[int, int, float]:
    url = base.rstrip("/") + path
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "txisd-visitor-sim/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, len(body), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, 0, time.monotonic() - t0
    except Exception:                                # noqa: BLE001
        return 0, 0, time.monotonic() - t0


def mcp(base: str, name: str, district: str) -> tuple[int, int, float]:
    method = "tools/call" if name not in ("server/discover", "tools/list") else name
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientCapabilities": {}}}
    headers = {"Content-Type": "application/json", "Mcp-Method": method,
               "MCP-Protocol-Version": "2026-07-28"}
    if method == "tools/call":
        params.update({"name": name, "arguments": {"district_number": district}})
        headers["Mcp-Name"] = name
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    t0 = time.monotonic()
    req = urllib.request.Request(base.rstrip("/") + "/mcp", data=payload.encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, len(r.read()), time.monotonic() - t0
    except Exception:                                # noqa: BLE001
        return 0, 0, time.monotonic() - t0


def districts(base: str) -> list[str]:
    """Real district numbers, weighted by enrolment — a visitor is far more
    likely to look up Houston than a 94-student district, and a uniform draw
    would understate the payload sizes that matter."""
    code, _, _ = get(base, "/fallback-index")
    if code != 200:
        return ["057905"]
    with urllib.request.urlopen(base.rstrip("/") + "/fallback-index", timeout=30) as r:
        rows = json.load(r).get("districts", [])
    out = []
    for d in rows:
        n = d.get("district_number")
        if not n:
            continue
        # Square-root weighting: big districts dominate, small ones still appear.
        out += [n] * max(1, int((d.get("students") or 100) ** 0.5 // 20))
    return out or ["057905"]


DB_ROUTES = ("/summary", "/peers", "/insights", "/turnarounds", "/breakdown",
             "/dollar", "/spending-detail", "/districts", "/anomalies",
             "/benchmarks", "/briefing")


def needs_db(path: str) -> bool:
    return any(k in path for k in DB_ROUTES)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--visitors", type=int, default=VISITORS)
    ap.add_argument("--sample", type=int, default=600,
                    help="journeys actually executed; the month is extrapolated")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--service-seconds", type=float, default=PROD_P50_SECONDS,
                    help="per-request service time for the concurrency estimate. "
                         "Defaults to the p50 measured against PRODUCTION, not "
                         "the local loopback figure.")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    print(f"modelling {args.visitors:,} visitors/month against {args.base}")
    print(f"measuring {args.sample:,} real journeys, then extrapolating\n")

    pool = districts(args.base)
    kinds = list(ARRIVALS)
    weights = [ARRIVALS[k] for k in kinds]

    per_kind = defaultdict(lambda: {"reqs": [], "bytes": [], "db": [], "lat": [],
                                    "fail": 0, "n": 0})
    codes = Counter()
    for _ in range(args.sample):
        kind = rng.choices(kinds, weights)[0]
        d = rng.choice(pool)
        reqs = nbytes = ndb = 0
        lat = 0.0
        failed = False
        for step in JOURNEYS[kind]:
            if step.startswith("MCP:"):
                code, size, t = mcp(args.base, step[4:], d)
            else:
                path = step.replace("{d}", d)
                code, size, t = get(args.base, path)
                if needs_db(path):
                    ndb += 1
            codes[code] += 1
            reqs += 1
            nbytes += size
            lat += t
            if code not in (200, 404):
                failed = True
        k = per_kind[kind]
        k["n"] += 1
        k["reqs"].append(reqs)
        k["bytes"].append(nbytes)
        k["db"].append(ndb)
        k["lat"].append(lat)
        k["fail"] += int(failed)

    # --- extrapolate ---------------------------------------------------------
    total_reqs = total_bytes = total_db = 0.0
    print(f"{'arrival':<34}{'share':>7}{'reqs':>7}{'KB':>9}{'db reqs':>9}{'p50 s':>8}")
    rows = []
    for kind in kinds:
        k = per_kind[kind]
        if not k["n"]:
            continue
        share = k["n"] / args.sample
        reqs = statistics.mean(k["reqs"])
        kb = statistics.mean(k["bytes"]) / 1024
        db = statistics.mean(k["db"])
        p50 = statistics.median(k["lat"])
        visitors = args.visitors * share
        total_reqs += visitors * reqs
        total_bytes += visitors * statistics.mean(k["bytes"])
        total_db += visitors * db
        rows.append({"arrival": kind, "share": round(share, 3),
                     "requests_per_visit": round(reqs, 1),
                     "kb_per_visit": round(kb, 1), "db_requests_per_visit": round(db, 2),
                     "p50_seconds": round(p50, 3),
                     "journeys_with_a_fault": k["fail"]})
        print(f"  {kind:<32}{share:>6.1%}{reqs:>7.1f}{kb:>9.1f}{db:>9.2f}{p50:>8.3f}")

    queries = args.visitors * QUERY_RATE
    total_reqs += queries
    gb = total_bytes / 1e9

    # --- the spike is what breaks ------------------------------------------
    spike_reqs = total_reqs * SPIKE_SHARE / SPIKE_DAYS
    peak_rps = spike_reqs / (SPIKE_HOURS * 3600)
    # A concurrency estimate from Little's law: arrivals x average service time.
    peak_concurrency = peak_rps * args.service_seconds
    peak_concurrency_p95 = peak_rps * PROD_P95_SECONDS
    db_share = total_db / total_reqs

    print(f"\n{'':-<64}")
    print(f"  requests/month           {total_reqs:>14,.0f}")
    print(f"  bandwidth/month          {gb:>14,.1f} GB   (Brotli on Vercel; measured uncompressed)")
    print(f"  database-backed requests {total_db:>14,.0f}   ({db_share:.1%} of all traffic)")
    print(f"  /query calls             {queries:>14,.0f}   ~${queries * DEEPSEEK_PER_CALL_USD:,.0f}/month DeepSeek")
    print(f"\n  a spike day ({SPIKE_SHARE:.0%} of the month over {SPIKE_DAYS} days, {SPIKE_HOURS}h each):")
    print(f"    peak                   {peak_rps:>14,.1f} req/s")
    print(f"    concurrent functions   {peak_concurrency:>14,.1f}   at p50 {args.service_seconds:.3f}s "
          f"(Vercel cap {VERCEL_FUNCTION_MAX_CONCURRENCY:,})")
    print(f"                           {peak_concurrency_p95:>14,.1f}   at p95 {PROD_P95_SECONDS:.3f}s")
    print(f"    concurrent DB requests {peak_concurrency_p95 * db_share:>14,.1f}"
          f"   (pooler {SUPABASE_POOLER_CONNECTIONS})")
    print("    service time is the PRODUCTION p50/p95; loopback latency would "
          "understate this ~20x")
    err = sum(v for k, v in codes.items() if k not in (200, 404))
    print(f"\n  status codes seen: {dict(codes)}")
    if err:
        print(f"  ** {err:,} of {sum(codes.values()):,} responses were not 200/404. If this run "
              f"had no\n     SUPABASE_DB_URL, those are the database-backed routes "
              f"failing, which means\n     the bandwidth figure is a FLOOR and the "
              f"database journeys were measured\n     in their degraded state. Re-run "
              f"with a database attached for the full figure.")

    # --- what gives way first ----------------------------------------------
    print(f"\n{'':-<64}\nFAULT LINES, in the order they bite\n")
    faults = []
    if db_share > 0:
        faults.append((
            "Supabase pauses after ~7 days idle (free tier)",
            f"{db_share:.0%} of requests touch the database. A paused project "
            f"degrades {total_db:,.0f} requests/month to the fallback path. The "
            f"pages still render — that was built — but the district summary, "
            f"peers and insights go dark."))
    faults.append((
        "/query is the only unbounded cost",
        f"At {QUERY_RATE:.1%} of visitors it is ${queries * DEEPSEEK_PER_CALL_USD:,.0f}/month. "
        f"At 10% it is ${args.visitors * 0.10 * DEEPSEEK_PER_CALL_USD:,.0f}. "
        f"sql/create_nlp_usage.sql is NOT applied in production, so the ceiling "
        f"is still per-serverless-instance rather than global — the one number "
        f"here that can run away."))
    if peak_concurrency_p95 > VERCEL_FUNCTION_MAX_CONCURRENCY * 0.5:
        faults.append(("Vercel function concurrency",
                       f"{peak_concurrency:,.0f} concurrent at peak against a "
                       f"{VERCEL_FUNCTION_MAX_CONCURRENCY:,} cap."))
    if peak_concurrency_p95 * db_share > SUPABASE_POOLER_CONNECTIONS * 0.5:
        faults.append(("Supabase pooler connections",
                       f"{peak_concurrency_p95 * db_share:,.0f} concurrent DB requests "
                       f"against {SUPABASE_POOLER_CONNECTIONS}."))
    faults.append((
        "Vercel Hobby is non-commercial",
        f"{gb:,.1f} GB/month uncompressed. Hobby includes 100 GB and forbids "
        f"commercial use; this volume is a Pro conversation either way."))
    for i, (title, detail) in enumerate(faults, 1):
        print(f"  {i}. {title}\n     {detail}\n")

    report = {"visitors_per_month": args.visitors, "sample": args.sample,
              "seed": args.seed, "by_arrival": rows,
              "requests_per_month": round(total_reqs),
              "bandwidth_gb_per_month": round(gb, 2),
              "db_requests_per_month": round(total_db),
              "db_share": round(db_share, 4),
              "query_calls_per_month": round(queries),
              "deepseek_usd_per_month": round(queries * DEEPSEEK_PER_CALL_USD, 2),
              "peak_requests_per_second": round(peak_rps, 2),
              "peak_concurrency_at_p50": round(peak_concurrency, 1),
              "peak_concurrency_at_p95": round(peak_concurrency_p95, 1),
              "service_seconds_input": args.service_seconds,
              "service_time_source": "measured against production, not this run",
              "non_2xx_responses": sum(v for k, v in codes.items() if k not in (200, 404)),
              "status_codes": dict(codes),
              "faults": [{"title": t, "detail": d} for t, d in faults]}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

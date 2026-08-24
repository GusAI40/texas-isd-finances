#!/usr/bin/env python3
"""Measure AI performance separately from data coverage.

Coverage asks "do we hold the information". This asks the other question:
**given information we demonstrably hold, does the agent return the right
number?** They are different failures with different fixes — more data will
never fix a retrieval bug, and a better model will never invent a column that
was not ingested.

So every question here is one the data CAN answer: each is generated from the
live `/district/{n}/summary` endpoint, which is also where its ground truth
comes from. A wrong answer is therefore an agent failure, never a gap.

Grading is deliberately mechanical. The expected figure must appear in the
answer, in one of its ordinary renderings ($23,420 / 23420 / 23,420.00). No
model judges another model's output, and a plausible-sounding paragraph with
the wrong number scores zero.

Usage:
    python scripts/ai_performance_probe.py --n 20
    python scripts/ai_performance_probe.py --n 20 --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://txisd.dev"
UA = {"User-Agent": "txisd-ai-probe/1.0 (+https://txisd.dev)"}


def get(url: str, timeout: int = 90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def post(url: str, payload: dict, timeout: int = 120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def renderings(value: float) -> list[str]:
    """Every ordinary way a correct answer might print this number."""
    v = float(value)
    i = int(round(v))
    out = {f"{i:,}", str(i), f"{v:,.2f}", f"{v:.2f}", f"{v:,.1f}"}
    # Millions/billions phrasing, which the agent uses for large totals.
    if abs(v) >= 1_000_000:
        out.add(f"{v/1_000_000:,.1f}")
        out.add(f"{v/1_000_000:,.2f}")
    if abs(v) >= 1_000_000_000:
        out.add(f"{v/1_000_000_000:,.2f}")
        out.add(f"{v/1_000_000_000:,.1f}")
    # Off-by-one from integer division in the view, and honest rounding.
    out.add(f"{i-1:,}")
    out.add(f"{i+1:,}")
    return sorted(out)


def build_cases(base: str, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    idx = json.loads((ROOT / "static/fallback_index.json").read_text())
    pool = [d for d in idx["districts"]]
    rng.shuffle(pool)

    cases: list[dict] = []
    forms = [
        ("spend_per_student", "How much did {name} spend per student in {year}?"),
        ("enrollment", "What was {name}'s enrollment in {year}?"),
        ("total_spend", "What were {name}'s total expenditures in {year}?"),
        ("instruction_spend", "How much did {name} spend on instruction in {year}?"),
        ("operating_spend", "What was {name}'s operating spend in {year}?"),
    ]
    for d in pool:
        if len(cases) >= n:
            break
        num = d["district_number"]
        try:
            rows = get(f"{base}/district/{num}/summary")
        except Exception:
            continue
        rows = [r for r in rows if r.get("enrollment")]
        if not rows:
            continue
        row = rng.choice(rows)
        metric, template = forms[len(cases) % len(forms)]
        truth = row.get(metric)
        if truth in (None, 0):
            continue
        cases.append({
            "district_number": num,
            "name": d["district_name"].title(),
            "year": row["year"],
            "metric": metric,
            "truth": truth,
            "question": template.format(name=d["district_name"].title(),
                                        year=row["year"]),
            "accept": renderings(truth),
        })
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--base", default=SITE)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--gap", type=float, default=3.0, help="seconds between calls")
    ap.add_argument("--out", default="data/ai_performance_probe.json")
    args = ap.parse_args()

    print(f"building {args.n} cases with ground truth from {args.base} …",
          file=sys.stderr)
    cases = build_cases(args.base, args.n, args.seed)
    print(f"  {len(cases)} cases ready", file=sys.stderr)

    results = []
    for i, c in enumerate(cases, 1):
        rec = dict(c)
        t0 = time.time()
        try:
            resp = post(f"{args.base}/query", {"question": c["question"]})
            answer = resp.get("answer") or ""
            structured = resp.get("structured")
            rec["answer"] = answer
            rec["has_structured"] = bool(structured)
            hit = any(a in answer.replace("$", "") or a in answer
                      for a in c["accept"])
            # A refusal is not a wrong answer; it is a different failure.
            refused = bool(re.search(
                r"(cannot|can't|unable|no data|not available|don't have)",
                answer, re.I)) and not hit
            rec["verdict"] = "correct" if hit else ("refused" if refused else "wrong")
        except urllib.error.HTTPError as e:
            rec["verdict"] = f"http_{e.code}"
            rec["answer"] = e.read()[:300].decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 — recorded, not swallowed
            rec["verdict"] = "error"
            rec["answer"] = str(e)[:300]
        rec["seconds"] = round(time.time() - t0, 1)
        results.append(rec)
        print(f"  {i:>3}/{len(cases)} {rec['verdict']:>8} {rec['seconds']:>5.1f}s  "
              f"{c['question'][:64]}", file=sys.stderr)
        if i < len(cases):
            time.sleep(args.gap)

    n = len(results)
    correct = sum(1 for r in results if r["verdict"] == "correct")
    wrong = sum(1 for r in results if r["verdict"] == "wrong")
    refused = sum(1 for r in results if r["verdict"] == "refused")
    errors = n - correct - wrong - refused

    # Wilson interval — at n=20 the normal approximation is not defensible.
    def wilson(k, m, z=1.96):
        if not m:
            return (0.0, 0.0)
        p = k / m
        d = 1 + z * z / m
        c = (p + z * z / (2 * m)) / d
        h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / d
        return (max(0.0, c - h), min(1.0, c + h))

    lo, hi = wilson(correct, n)
    summary = {
        "n": n, "correct": correct, "wrong": wrong, "refused": refused,
        "errors": errors,
        "accuracy": correct / n if n else 0.0,
        "accuracy_ci95_wilson": [lo, hi],
        "median_seconds": sorted(r["seconds"] for r in results)[n // 2] if n else 0,
        "base": args.base,
        "seed": args.seed,
        "note": "Every question is answerable from v_finance_summary and its truth "
                "comes from the same endpoint the site serves. A wrong answer here "
                "is an agent failure, not a data gap.",
        "results": results,
    }
    out = ROOT / args.out
    out.write_text(json.dumps(summary, indent=1))
    print(f"\nAI ACCURACY  {correct}/{n} = {correct/n:.0%}  "
          f"(95% Wilson {lo:.0%}–{hi:.0%})")
    print(f"  wrong {wrong} · refused {refused} · errors {errors}")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

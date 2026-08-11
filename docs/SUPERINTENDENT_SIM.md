# 1,000 superintendents: where this breaks

Run 2026-08-10 against live production. 1,000 simulated superintendents drawn
from the real district population and weighted by enrolment, six motives, 5,138
real HTTP requests at 8 concurrent, 474 seconds wall clock. Seeded
(`SEED = 20260810`) so a fix can be measured against the same population.

    python scripts/simulate_superintendents.py --base https://txisd.dev

**Headline: 830 of 1,000 journeys completed with no fault. The 170 that failed
almost all failed the same way — a 200 response with nothing in it.**

---

## First, what is NOT a fault

The run recorded 88 connection failures and a p99 of 30,156 ms. **That is the
agent proxy this simulation ran through, not production.** Two things establish
it:

- the failures are spread evenly across all 23 distinct steps, including the
  static portal page and `/forensics` — an app fault concentrates somewhere;
- a plain sequential `curl` loop at concurrency 1 reproduces it (1 failure in
  12, in 1.1 s).

Real production latency in the same run: **p50 295 ms, p95 562 ms.** That is
healthy and is not a fault line. Reporting the 30-second figure as a production
problem would have been the easiest mistake available here.

---

## The fault lines, ranked by students behind them

Counted exactly from the artefacts, not sampled — a dead end is a property of
the data, so it can be enumerated.

| Fault | Districts | Students | Where it shows |
|---|---:|---:|---|
| **No peer ever turned around** | ~48% of requests | **1,567,284** | `/turnarounds` returns `[]` |
| No tax figure | 188 (15.6%) | 440,240 | "your tax bill" is blank |
| No bond election on record | 266 (22.1%) | 463,784 | the whole bond section is empty |
| No named peer who does better | 58 (4.8%) | 77,580 | "who does better" is empty |
| No equity record | 115 (9.6%) | 33,362 | equity section empty |
| No 17-year trend (<8 years) | 24 (2.0%) | 12,678 | trajectory empty |
| Small district (noisy per-student) | 382 (31.8%) | 95,471 | figures shown but unreliable |

**331 districts — 27.5% of them, 533,917 students, 9.7% of Texas — have at
least one section that renders empty.**

### Broken journeys by motive

| Motive | Broken | Rate |
|---|---:|---:|
| **benchmarking** | 60 / 105 | **57.1%** |
| budget_season | 48 / 288 | 16.7% |
| bond_planning | 20 / 150 | 13.3% |
| board_prep | 24 / 235 | 10.2% |
| press_inquiry | 12 / 127 | 9.4% |
| recruitment | 6 / 95 | 6.3% |

Benchmarking is the worst journey in the product by a factor of three, and it
is the one a superintendent runs when they are actually trying to improve.

---

## Fault line 1: emptiness is thrown away

`/district/{n}/turnarounds` looks for a structural peer that reversed a
sustained deficit (≥2 deficit years then ≥2 surplus years) or a sustained
enrolment decline. That is a narrow pattern, and for roughly half of requests
no peer matches it. The endpoint correctly returns `{"turnarounds": [],
"peers_scanned": N}`.

**The endpoint is honest. The product is not**, because an empty list renders as
an empty section — and the emptiness is itself the most interesting finding on
the page:

> None of your 14 structural peers reversed a sustained deficit in seventeen
> years.

That sentence is *stronger* than a list would have been. It is currently
discarded. The same is true of every row in the table above: "no bond election
on record since 1958" is a fact about a district, not an absence of one.

**This is the single highest-value fix in the product, and it needs no new
data.** It is a rendering decision, not an ingest problem.

## Fault line 2: nothing distinguishes "no data" from "no finding"

A charter has no tax figure because it levies no property tax. A district with
withheld tax data has one that could not be verified. A district with no bond
history never went to the voters. Today all three render the same way — blank —
so the reader cannot tell "we don't know" from "this didn't happen", and those
mean opposite things.

## Fault line 3: payload weight

Uncompressed at the client, medians: `/district-geo` 518 KB, `/briefing`
348 KB, the portal 224 KB, `/forensics/texas` 210 KB, `/trends/texas` 158 KB.
Brotli cuts these substantially on the wire, but the geo payload is still the
heaviest thing a phone is asked to parse, and the parse is not compressed.

---

## What this run does not cover

- **Only one network path.** Real-user latency from Texas on mobile is not
  measured here.
- **No browser.** These are API journeys; JavaScript execution, render time and
  layout are out of scope.
- **No concurrency ceiling.** Eight at a time is polite, not a load test. What
  happens at 500 concurrent — and what a paused Supabase does under that — is
  untested.
- **Motive weights are modelled**, not observed. The district population and
  enrolment weighting underneath them are real.

## Re-running after a fix

    python scripts/simulate_superintendents.py --base https://txisd.dev

Same seed, same 1,000 superintendents, same districts. The number that should
move is **clean journeys (830/1,000)** and the **benchmarking rate (57.1%
broken)**.

# Would a geographic map teach the public anything new?

**Monte Carlo over real Texas geography · seed 20260726 · 100,000 simulated
visitors · reproduce with:**

```bash
python scripts/simulate_map_value.py \
  --shapefile <dir>/tl_2024_48_unsd --snapshot data/tea_snapshot_district.csv
```

## Why this simulation is built differently

Our first simulation (`docs/UX_RESEARCH.md`) modelled 1,000 administrators
using persona priors *we chose*. That is legitimate for ranking UI demand, but
it cannot answer "is there new information here" — feed it assumptions and it
hands them back.

So this one puts almost nothing in by hand:

- **Visitors are placed by real enrolment.** A simulated visitor is as likely
  to land in a district as a Texas child is to attend one.
- **Adjacency is real.** Computed from Census TIGER 2024 polygons by shared
  boundary vertices — TIGER is topologically built, so neighbouring districts
  share exact coordinates. 1,017 districts, 2,863 shared borders, median 5
  neighbours each.
- **The comparison baseline is the live site.** "Statistical peers" are the
  exact k-NN peers `static/map_data.json` already serves.

The only judgement calls are two materiality thresholds, and both are swept.

## Coverage, stated first

The map can cover **1,008 districts holding 4,928,243 of 5,377,659 Texas
students — 91.6%.** The missing 8.4% attend **charter districts, which have no
geographic boundary at all.** They are not an oversight; they are not
geographic entities. Any map we ship has to say so on its face, or it will
quietly imply those children don't exist.

## What a visitor gains

| | Share of visitors |
|---|---:|
| Sees a **neighbouring district the site never shows them** | **100.0%** |
| **None** of their neighbours are among their statistical peers | **64.7%** |
| Lives where **≥10 districts sit within ~38 km** ("which district am I even in?") | **77.6%** |
| Has a neighbour with **similar student poverty but markedly better teacher retention** | **7.3%** |

And the number that settles the design question:

> Median neighbours per district: **5**
> Median of those that are also statistical peers: **0**

**The map is not a prettier version of the peer list. It is a different list.**
Every visitor gets comparisons the site cannot currently produce, and for
nearly two-thirds, geography is *entirely* new information.

## The threshold-sensitive one

Finding 4 — "a neighbour with similar students keeps teachers much better" —
depends on what counts as *similar* and *better*. It should never be quoted as
a single number:

| Similar poverty within | Better turnover by | Share of visitors |
|---:|---:|---:|
| ±4 pts | ≥5 pts | 13.0% |
| ±4 pts | ≥8 pts | 5.6% |
| ±4 pts | ≥12 pts | 2.2% |
| ±6 pts | ≥8 pts | **7.3%** |
| ±10 pts | ≥5 pts | 19.8% |
| ±10 pts | ≥12 pts | 4.4% |

**Range: 2.2%–19.8%.** The honest statement is "between roughly 1 in 50 and 1
in 5 Texas students attend a district whose immediate neighbour, serving
similar students, retains teachers substantially better." Where it does
happen, the median gap is **10.2 percentage points** of annual turnover.

## What this means for the public

1. **Everyone gets a new comparison.** Not a redesign — new information, for
   100% of visitors.
2. **For most people, "who is like us" and "who is next to us" are disjoint
   sets.** Median overlap is zero. Those two questions have different answers
   and only one of them is currently answerable here.
3. **Three-quarters of Texas students live somewhere district identity is
   genuinely confusing** — ten or more districts within a half-hour drive.
   Address→district lookup isn't convenience for them; it's the difference
   between using this site and bouncing off it.
4. **A meaningful minority can see a working counter-example next door** — a
   district with the same students that keeps its teachers. Given that
   turnover predicts results ~1,000× better than spending per student
   (`docs/WHAT_A_DOLLAR_BUYS.md`), that is the most actionable single fact
   this project can hand someone.

## What this simulation cannot tell you

- **Whether anyone visits, or acts.** It measures *available information*, not
  persuasion, traffic, or behaviour change.
- **Whether any difference is caused by anything a district did.** Adjacency
  controls for region, economy, weather and labour market — which is why it is
  more persuasive than a regression — but it does not control for district
  size, urbanicity, governance, or a single disruptive year.
- **Anything about charter students.** 8.4% of Texas students are outside this
  analysis entirely.
- Turnover is a **single year** (2024). Small districts swing hard; the
  "better neighbour" test uses no minimum size, so some pairs will be noise.

## Sources

Census TIGER/Line 2024 Unified School Districts, Texas (FIPS 48) — public
domain. Joined to TEA district numbers by normalised name at **99.0%**
(996 of 1,006 polygons); the ten misses are spelling variants. TEA Snapshot
2024 for turnover, poverty and enrolment.

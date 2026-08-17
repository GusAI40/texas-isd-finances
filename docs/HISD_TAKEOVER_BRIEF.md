# Did the state takeover of Houston ISD change results? A briefing for reporters

*Prepared 2026-08-17 · Texas ISD Financial Resource Guide (txisd.dev) · an
independent analysis of state-published data, not a TEA product. Built with
AI assistance across the entire system; every figure below is re-derived
from the state's own files by automated tests, and everything needed to
check or dispute it is public and listed at the end.*

---

## The finding, in one paragraph

Two school years after the Texas Education Agency replaced Houston ISD's
elected board with appointed managers (June 2023), Houston's STAAR results
at the **Meets grade level** bar rose **5.5 points** against its last
untested-by-the-takeover year, while thirteen comparison districts —
chosen *before looking at outcomes*, on size and poverty alone — moved
**0.0** on the same measure over the same window. Run the identical
calculation for every district in Texas as a placebo, and Houston ranks
**50th of 1,166** (top 4.3%) — and **1st of the 30 districts with 40,000+
students**, the only fair pool for a district of its size. The result
survives the three standard ways such a number can be fake, each tested
rather than assumed. It also has an exception that belongs in any honest
account: **special education students went backwards** relative to the
comparison districts (−1.8 points, 2024→2025) while every other reported
group gained.

## Why Houston's own before-and-after can't settle this

Both sides of the takeover argument quote Houston's own numbers. Those
numbers cannot answer the question, because every Texas district was
climbing out of the same pandemic hole at the same time — a district that
did nothing at all posted gains in 2024 and 2025. The only informative
comparison is against districts that were in the same hole and were **not**
taken over.

**Design:** difference-in-differences. The comparison group is every Texas
district with at least 40,000 students and at least 60% economically
disadvantaged students *as of 2023* — criteria fixed on pre-takeover traits
only, so the pool cannot be picked to flatter the answer. Thirteen
districts qualify. TEA's "year" is the school year ending, so spring 2023
testing happened months before the managers arrived: 2023 is the last
untreated year, 2024 is year one, 2025 is year two. The headline change is
the average of the two post years minus 2023.

## The trajectory (Meets grade level, all subjects)

| Year | Houston | Comparison (13-district mean) |
|---|---|---|
| 2018 | 42.0 | 42.8 |
| 2019 | 44.0 | 44.8 |
| 2021 | 33.0 | 31.5 |
| 2022 | 43.0 | 40.8 |
| **2023** (last untreated) | **41.0** | **42.2** |
| 2024 (year one) | 44.0 | 41.2 |
| 2025 (year two) | 49.0 | 43.2 |

(2020 is absent because STAAR was not administered.)

## The three ways this could be fake — each tested, results published

**1. Houston might already have been pulling ahead.** It wasn't. Over the
five pre-takeover test years, Houston's trend was −0.30 points/year and the
comparison group's was −0.53 — near-parallel, slightly *against* Houston.
The difference-in-differences design holds.

**2. A five-point swing might just be normal noise.** The identical
calculation was run for all 1,166 Texas districts with sufficient data as a
placebo. Houston lands 50th — the top 4.3% — and **first of the 30
large districts**. Big districts are statistical flywheels; their averages
barely move. Houston's did.

**3. The student body might have changed.** If lower-scoring students left,
the average rises with no child learning more. Houston's enrolment fell
3.0% across the transition (189,290 → 183,603) versus 1.3% for the
comparison districts — a real difference, reported, not buried. But the
share of economically disadvantaged students held flat (79.5% → 79.6%), so
the students who left were not disproportionately poor. A composition
effect cannot be fully excluded; the poverty share is the evidence that it
is unlikely to carry a 5.5-point headline.

## Who the gains reached — and who they didn't

Measured 2024→2025 (a different, one-year window — TEA's by-group STAAR
file; stated so the two tables are never conflated):

| Student group | Houston | Comparison | Difference |
|---|---|---|---|
| All students | +5.0 | +2.0 | **+3.0** |
| Low income | +4.0 | +1.7 | **+2.3** |
| Learning English | +3.0 | −1.0 | **+4.0** |
| **Special education** | **−1.0** | **+0.8** | **−1.8** |
| African American | +5.0 | +2.1 | **+2.9** |
| Hispanic | +5.0 | +1.8 | **+3.2** |

The special education line is the story inside the story. Every other
reported group beat the comparison districts; the students with the least
margin for a bad year did not. Any account that quotes the +5.5 without
this line is quoting half the result.

## The thirteen comparison districts

Same calculation, same window (mean of 2024–2025 minus 2023):

Aldine +4.0 · Socorro +1.5 · Fort Worth +1.0 · Garland +1.0 · Pasadena
+0.5 · United (Laredo) 0.0 · Dallas 0.0 · San Antonio 0.0 · Killeen −0.5 ·
El Paso −1.0 · Arlington −1.0 · Alief −2.0 · IDEA Public Schools −3.5.

Houston, at +5.5, is first of the fourteen.

## What this does NOT show

Quoted from the analysis's own published limits, because they are part of
the result:

- **One treated district.** There is no meaningful p-value for a sample of
  one and none is claimed; the placebo rank across every Texas district is
  the honest substitute.
- **Two years of results is short.**
- **"The takeover" is a bundle** — a new board, a new superintendent, the
  NES curriculum, heavy staff turnover, school closures. This measures
  whether results moved, not *which decision* moved them. It is not a
  verdict on the policy, and it does not weigh the costs (teacher
  departures, community opposition, closed campuses) against the gains.
- **Composition cannot be fully excluded** (see threat 3 above).

## Check it yourself

- Interactive version: **https://txisd.dev/takeover/houston** (JSON) and
  the "State takeover" section of **https://txisd.dev/?d=101912**.
- Inputs are TEA's own public files: the district Snapshot
  (2018–2024) and the district STAAR files (2024, 2025) — both listed with
  download links at **https://txisd.dev/sources**.
- The full method is code, in public:
  `scripts/build_takeover_data.py` in the repository
  **https://github.com/GusAI40/texas-isd-finances** — the comparison rule,
  the placebo, the pre-trend test, all of it. The artifact rebuilds
  byte-identically from source in CI.
- This site is built with AI assistance and published as-is with a margin
  of error; full disclosure at **https://txisd.dev/transparency**.

*Contact: via the repository, or gus@ubntag.com.*

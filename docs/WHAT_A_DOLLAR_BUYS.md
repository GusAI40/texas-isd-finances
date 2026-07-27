# What a School Dollar Actually Buys

**Findings from joining 17 years of Texas district spending to 16 years of
TEA Snapshot district data — 19,382 district-years, fiscal 2009–2024.**

Reproduce everything here with:

```bash
# fetches the 32 source files straight from TEA, then normalises them
python scripts/ingest_tea_snapshot.py --download --src data/tea_snapshot \
       --out data/tea_snapshot_district.csv
python scripts/analyze_outcomes.py --finance data/texas_finance_clean.csv \
       --snapshot data/tea_snapshot_district.csv --out docs/findings_outcomes.json
```

`data/*.csv` is gitignored — datasets are regenerated, never committed — so
the ingest downloads its own inputs and the whole chain runs from a clean
checkout.

---

## Read this first

Every number below is an **association measured across districts**. None of it
is causal, and the difference matters enormously here.

Districts serving harder-to-serve students both **spend more** (need-based
state and federal funding sends money where need is) and **post lower raw
scores**. So a naive chart of "spending vs test scores" produces a *negative*
line, and that line has been used for years to argue that school money is
wasted. It shows nothing of the kind. It is a portrait of where need is
concentrated.

That confound is why every finding below controls for student need —
percentage economically disadvantaged, percentage emergent bilingual,
percentage in special education — **before** comparing anything.

"Beating expectations" means scoring above what a district's student
demographics alone predict. It is a question worth asking about a district,
never a verdict on it, and never a judgement of its teachers.

---

## Finding 1 — Who you teach explains far more than what you spend

Share of the variation between districts explained:

| Outcome | Student need alone | Spending alone | Spending adds, *after* need |
|---|---:|---:|---:|
| STAAR % at/above grade level | **33.4%** | 0.6% | **0.0%** |
| 4-year graduation rate | 8.3% | 0.0% | 0.9% |
| Attendance rate | 8.1% | 1.0% | 0.1% |

Once you know a district's student population, its total spending per student
tells you **essentially nothing more** about its measured results. The raw
correlation between spending and STAAR performance is −0.077 — slightly
negative, entirely explained by need.

This is not "money doesn't matter." It is narrower and more useful: **the
overall size of the budget, as budgets are currently allocated, does not
distinguish districts that do better than expected from those that do worse.**
Which raises the real question — does anything?

## Finding 2 — Yes. Teacher stability, and it is not close

Same test, applied fairly to every lever: how much does each explain of the
part of the result that student need does *not* already explain?

| Lever | Raw correlation | Explains after need |
|---|---:|---:|
| **Teacher turnover rate** | −0.394 | **10.12%** |
| % teachers with ≤5 years experience | −0.375 | 7.97% |
| Teacher average years of experience | +0.318 | 6.79% |
| % of spending on instruction | +0.233 | 2.13% |
| Students per teacher | −0.102 | 1.70% |
| Average teacher salary | +0.066 | 0.86% |
| **Spending per student** | −0.077 | **0.01%** |

> ### Correction (2026-07-27) — the wrong bar was being reported
>
> Everything below originally used TEA's **"Approaches grade level"** bar. That
> is the lowest of three, and it is not grade level. Statewide in SY 2024-25:
> **74.2%** reach Approaches, **46.5%** reach **Meets**, 17.6% Masters. A reader
> told "74%" hears "at grade level," so the portal now reports **Meets**
> throughout.
>
> This was not only a labelling problem. Scoring districts on Approaches rather
> than Meets moves **35 of the top 100** "reliably beats expectations"
> districts, so modelling one bar while displaying another would have named
> outperformers on a measure nobody sees. Meets begins in 2018, costing five
> years of span, and costs nothing in reliability: split-half r = **0.913**
> against 0.910. The need model also fits better on Meets (**50.1%** of the
> spread explained, against 42.3%).
>
> **The effect sizes changed with the bar, and so did the ranking.** Re-measured
> at Meets over 3,538 three-year windows in 1,193 districts:
>
> | Change a district made over 3 years | Effect on % Meeting grade level | 95% CI |
> |---|---:|---|
> | Raise average teacher pay $5,000 | **+0.86** | +0.48 to +1.23 |
> | Shift 5% more of budget to teaching | +0.42 | −0.11 to +0.94 (crosses zero) |
> | Cut class size by 2 students | +0.37 | +0.20 to +0.55 |
> | Cut teacher turnover by 10 points | +0.30 | −0.06 to +0.65 (crosses zero) |
> | **Spend $2,000 more per student** | **+0.15** | **−0.04 to +0.33 (crosses zero)** |
>
> The headline holds — money still buys nothing measurable — but **teacher pay
> is now the largest identifiable lever, and turnover no longer separates from
> zero.** The earlier correction below overstated turnover for a second reason:
> it was measured on the wrong bar.

> ### Correction (2026-07-26) — this table describes, it does not forecast
>
> Everything in the table above compares **different districts to each other**.
> That makes it a description of which districts differ, not a measure of what
> happens if one district changes something. Re-running the question as a
> **within-district** comparison — the same district against itself over three
> years, 5,887 windows across 1,210 districts, with year effects and errors
> clustered by district — gives much smaller numbers:
>
> | Change a district actually made, over 3 years | Effect on STAAR | 95% CI |
> |---|---:|---|
> | Spend $2,000 more per student | **+0.08** | −0.21 to +0.37 — indistinguishable from zero |
> | Cut teacher turnover by 10 points | +0.43 | +0.15 to +0.71 |
> | Cut class size by 2 students | +0.59 | +0.36 to +0.83 |
>
> The *ranking* of the levers survives; the *magnitude* does not. Turnover is
> real but small — it is better read as a symptom of whatever makes a district
> work than as a dial that produces 10% of the variance when turned.
>
> What is large is the persistent difference between districts: split-half
> reliability of +0.91 across independent years, with a 20.2-point spread
> between the top and bottom deciles, of which **only 23% is explained by every
> staffing and money variable TEA publishes**. See `scripts/build_economics_data.py`.

Teacher turnover explains roughly **1,000 times more** of the unexplained
variation than spending per student does. The top three levers are all the
same underlying thing: **whether experienced teachers stay**.

Note what this does *not* say. Average teacher salary explains only 0.86% on
its own — so "pay more" is not a one-step answer. Pay is weakly related to
turnover (r = −0.144) while poverty is more strongly related to it (r =
+0.268). Districts serving the highest-need students lose teachers fastest,
and that is where the outcome gap widens.

## Finding 3 — Texas spending still tracks property wealth

Districts grouped by taxable property value per pupil, fiscal 2024:

| Property wealth | Districts | Median value/pupil | Median spend/student | Median % econ. disadv. | Median teacher pay | Median turnover |
|---|---:|---:|---:|---:|---:|---:|
| Poorest 20% | 241 | $0 | $14,281 | **77%** | $57,042 | **28%** |
| 2nd | 240 | $338,718 | $14,363 | 68% | $56,336 | 20% |
| Middle | 241 | $514,196 | $13,577 | 62% | $55,819 | 20% |
| 4th | 240 | $730,522 | $14,371 | 60% | $56,694 | 21% |
| Richest 20% | 241 | $1,400,763 | **$16,472** | 58% | $57,699 | 21% |

After decades of equalization, the wealthiest fifth of districts by property
value still spend about **15% more per student** than the poorest fifth —
while serving students with 19 percentage points *less* economic disadvantage.
The poorest fifth also carries a **28% teacher turnover rate**, eight points
above every other group.

Read Findings 2 and 3 together and the mechanism is uncomfortable: the
districts whose students most need experienced teachers are the districts
losing teachers fastest, and they are not spending more to counter it.

*(The "$0" median for the poorest quintile is real: it is dominated by charter
districts, which levy no property tax. That is a property-wealth statement, not
a data error — see limits below.)*

## Finding 4 — The hidden treasures

602 districts spent below the state median in 2024. These 15 beat what their
demographics predict by the widest margin **while spending less than half the
state does**:

| District | % econ. disadv. | Spend/student | Spending percentile | STAAR actual | Predicted | Gap |
|---|---:|---:|---:|---:|---:|---:|
| Texhoma ISD | 68% | $11,178 | 7th | 98 | 72 | **+26** |
| Rise Academy | 86% | $10,528 | 4th | 91 | 67 | +24 |
| Mumford ISD | 69% | $10,515 | 3rd | 97 | 74 | +23 |
| Amigos Por Vida–Friends For Life | 98% | $12,040 | 17th | 86 | 64 | +22 |
| Houston Gateway Academy | 89% | $9,954 | 2nd | 86 | 68 | +18 |
| Pittsburg ISD | 77% | $13,743 | 40th | 87 | 69 | +18 |
| Alief Montessori Community School | 77% | $9,941 | 2nd | 87 | 71 | +16 |
| Ingram ISD | 66% | $13,937 | 43rd | 88 | 72 | +16 |

These are **questions, not conclusions**. Small districts show more extreme
values for arithmetic reasons, charter districts operate under different rules,
and a single year's STAAR result is noisy. What the list is good for: telling a
school board with a similar student population exactly whom to call.

---

## Limits — read before citing

- **Association, not causation.** Nothing here identifies a cause. A district
  could beat expectations because of leadership, a stable veteran staff, a
  smaller and more cohesive community, or measurement noise.
- **The need model explains 33.4% of STAAR variation.** Two-thirds remains
  unexplained by demographics. Some of that is real district difference; some
  is noise. Do not treat a residual as a score.
- **Snapshot vs our finance data disagree by a median 2.9%** on operating
  spending per pupil, because the two use slightly different enrollment
  denominators and reporting vintages. Both are TEA's own figures. Use the
  right one for the question, and don't mix them within a single calculation.
- **The testing standard changed.** 2013–2017 reports a phase-in satisfactory
  rate; 2018 onward reports "at Approaches grade level." The ingest records
  which standard each row used in `test_standard`. **Do not draw a trend line
  across that break.**
- **2020 and 2021 are pandemic years.** Testing was cancelled or disrupted.
- **Accountability ratings are absent for 2023 and 2024** — TEA's ratings were
  subject to litigation and are not in those Snapshot files.
- **Charter districts are included** and differ structurally from ISDs: no
  property tax base, different facilities funding, different student
  populations by design. Filter or note them for any wealth comparison.
- **Masked values are missing, not zero.** TEA suppresses cells under FERPA;
  the ingest preserves them as null rather than inventing a measurement.

## Source

TEA Snapshot, District and Charter Detail Data —
<https://rptsvr1.tea.texas.gov/perfreport/snapshot/download.html>
(`POST /perfreport/snapshot/push.cgi`, `level=district`, `set=<YY>`,
`suf=.dat|.lyt`). Fields are mapped by their layout-file *description* rather
than by column name, because TEA embeds the reporting year in every variable
name and renames measures between years.

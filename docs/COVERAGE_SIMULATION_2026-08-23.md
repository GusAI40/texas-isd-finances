# 90-Day Monte Carlo Data Coverage & Answerability Test

**Run date** 2026-08-23 · **Simulator** `scripts/coverage_simulation.py` ·
**Raw output** `data/coverage_simulation.json` (993 KB) ·
**AI probe** `scripts/ai_performance_probe.py`

---

## 1. Bottom line

> Based on a 90-day Monte Carlo simulation of 10,828 users asking 60,042
> questions, the application can currently answer **67.1%** of realistic user
> inquiries completely and correctly from the data it actually holds
> (95% CI **66.8%–67.4%**).

**Overall grade: D.**

The portal is excellent at the questions it was built to answer and has a
structural hole underneath the questions its largest audience actually asks.

---

## 2. What was measured, and what was deliberately not

Two different scores, kept apart because they have different fixes:

| | Question | Result |
|---|---|---|
| **Data coverage** | Do we possess the information at all? | **67.1%** (n=60,042, deterministic) |
| **AI performance** | Given data we hold, does the agent return the right number? | measured separately, small n — §11 |

More data will never fix a retrieval bug; a better model will never invent a
column nobody ingested. Reporting one number for both would hide whichever is
actually broken.

**No language model was asked to grade itself.** Every one of the 60,042
inquiries was resolved by probing the real artefacts and the real database
views for the district that was actually sampled. A question counts as
answerable only when every field its answer needs resolves to a real value.

---

## 3. Simulation size and method

| Parameter | Value |
|---|---|
| Users simulated | 10,828 (5 seeds × ~2,166) |
| Days | 90 |
| Total inquiries | 60,042 |
| Monte Carlo seeds | 5 (1–5), plus 4 persona-mix variants |
| Question templates | 105 across 14 categories |
| Districts in scope | 1,202 |
| District sampling | enrollment^0.5 weighted; 12% roam for public personas, 45% for professionals |
| Reproducibility | `python scripts/coverage_simulation.py --seeds 5 --users 1000 --inquiries 12000` |

**The question bank is written from user needs, not from the schema.** This is
the single most important design decision here. A bank derived from the fields
we hold would score near 100% and measure nothing. Roughly a third of the
templates are things the portal cannot answer at all — they are in the bank
precisely because people ask them.

**An honest refusal is not automatically an answer.** `src/absences.py`
separates three kinds of nothing, and the grading follows it:

- `NOT_APPLICABLE` — "a charter levies no property tax" → **counts as answered.**
  The question has a definitive answer and the site gives it.
- `DID_NOT_HAPPEN` — "no bond election was ever held here" → **counts as answered.**
- `NOT_MEASURED` — "we do not have this" → **does not count.** Saying so is the
  right behaviour, but the reader still leaves without the fact.

The grader was validated against a population the repo documents independently:
it finds exactly **188** districts with no tax-bill figure, of which **183 are
charters** (answered: not applicable) and **5 are not** (not measured) — matching
`absences.py`'s own docstring without being told the number.

### Grading scale

| Grade | Meaning | Share |
|---|---|---|
| **A** | Every field the answer needs resolves | **67.1%** (40,281) |
| **B** | Partially answerable — a documented substitute covers part | **3.5%** (2,114) |
| **C** | Data never collected | **20.5%** (12,297) |
| **D** | **Data is held but no published surface exposes it** | **8.9%** (5,350) |

---

## 4. Headline scores

| Score | Value | Grade |
|---|---|---|
| **Full answerability** | **67.1%** (CI 66.8–67.4) | **D** |
| Useful answerability (A+B) | 70.6% | C |
| **Business-weighted** (critical×5, high×3, normal×1) | **64.8%** | **D** |

**The weighted score is lower than the raw score, and that is the finding.**
The portal answers its easy questions better than its important ones. A system
that inverted this would be in better shape than its headline suggested; this
one is in worse.

### Robustness — the persona mix is an assumption, so it was varied

| Persona mix | Full | Useful | Weighted |
|---|---|---|---|
| Assumed (this report) | 67.0% | 70.6% | 64.2% |
| Flat — all personas equal | 68.5% | 72.0% | 66.4% |
| Public-heavy (60% parents) | **63.5%** | 67.2% | 61.3% |
| Professional-heavy | 69.1% | 72.4% | 66.6% |

The answer stays in a 63–69% band and grade D under every mix, so the headline
does not rest on my guess about who shows up. The *direction* is the useful
part: **the more public the audience, the worse coverage gets**, because
ordinary people ask campus-level and forward-looking questions and the portal is
district-level and historical.

---

## 5. Coverage by category

| Category | Questions | Full | Partial | Never collected | Held, unreachable | Coverage | Grade |
|---|---:|---:|---:|---:|---:|---:|:--:|
| cross_system | 513 | 509 | 4 | 0 | 0 | 99.2% | A |
| trend | 4,492 | 3,645 | 0 | 847 | 0 | 81.1% | B |
| historical | 3,487 | 2,704 | 0 | 783 | 0 | 77.5% | C |
| ambiguous | 912 | 698 | 1 | 213 | 0 | 76.5% | C |
| comparison | 6,698 | 5,065 | 826 | 807 | 0 | 75.6% | C |
| current_status | 12,968 | 9,295 | 0 | 3,673 | 0 | 71.7% | C |
| geographic | 724 | 471 | 0 | 253 | 0 | 65.1% | D |
| exceptions | 6,388 | 4,080 | 71 | 1,100 | 1,137 | 63.9% | D |
| operations | 4,239 | 2,692 | 0 | 1,547 | 0 | 63.5% | D |
| **financial** | **13,340** | 8,124 | 0 | 1,570 | **3,646** | **60.9%** | **D** |
| root_cause | 3,077 | 1,636 | 823 | 235 | 383 | 53.2% | F |
| recommendation | 1,141 | 568 | 389 | 0 | 184 | 49.8% | F |
| forecast | 1,824 | 794 | 0 | 1,030 | 0 | 43.5% | F |
| out_of_scope | 239 | 0 | 0 | 239 | 0 | 0.0% | F |

**`financial` is the largest category and scores D.** That is the portal's
entire reason to exist, and 3,646 of its failures are data the project already
holds.

### By audience

| Persona | Share of users | Coverage | Grade |
|---|---:|---:|:--:|
| vendor_prospect | 3% | 79.6% | C |
| district_leader | 11% | 71.2% | C |
| board_trustee | 6% | 70.5% | C |
| policy_researcher | 8% | 69.8% | D |
| journalist | 9% | 65.6% | D |
| realtor_relocating | 5% | 62.3% | D |
| taxpayer_voter | 16% | 62.2% | D |
| **parent_resident** | **42%** | **60.7%** | **D** |

**The biggest audience is the worst served.** Parents are 42% of simulated
traffic and get the lowest coverage of any group.

---

## 6. The single biggest finding: 14 columns nobody can reach

**8.9% of all inquiries — 5,350 of 60,042 — fail against data this project
already has in its own database.**

The chain, verified rather than assumed:

1. `scripts/import_to_supabase.py` builds `texas_school_finance` with pandas
   `to_sql` straight from the cleaned CSV, so **every CSV column is a table
   column** (140 of them).
2. `static/trend_data.json` → `meta.reclassification_check.functions = **16**`,
   computed at build time from that CSV by `build_trend_data.py:181`
   (`[c for c in d.columns if c.startswith("all_funds_") and "fct" in c]`).
   So there are 16 PEIMS function-code columns in the table.
3. `sql/create_tables.sql` — `v_finance_summary` exposes **one** of them
   (`instruction_transfer_expend_fct11_95`). The artefacts publish a second
   (`security_monitoring_service_expend_fct52`).
4. `sql/create_nlp_role.sql:65-66` — `nlp_reader` holds `SELECT` on exactly
   two views and nothing else, under a blanket `REVOKE ALL`.

**Result: 14 function-code columns — administration, transportation, food
service, counselling, health services, plant maintenance and the rest — are in
the production database and reachable by no published surface.** Not the API,
not the artefacts, not the MCP tools, not the natural-language agent.

Every one of these fails today, and each is a question people plainly ask:

- *How much does {district} spend on administration?* (critical)
- *What does {district} spend on buses?*
- *What does {district} spend on school meals?*
- *Does {district} spend enough on counsellors?*
- *How much does {district} spend on football?*
- *Where can {district} cut without touching the classroom?* (critical)
- *Which districts spend the most on administration?*
- *Which districts cut instruction while raising administration?*
- *Is {district} wasting money?* — the flags layer answers part; the spend
  detail that would substantiate "waste" is unreachable.

This is also the **cheapest** item on the entire roadmap. It is a view
definition and a grant, not an ingest. No new source, no new licence, no new
freshness watchdog. The data has been sitting there the whole time.

---

## 7. Root causes of every non-A result

| Root cause | Inquiries | Kind |
|---|---:|---|
| Function-level spend held but unexposed | 3,646 | **D — reachable by nobody** |
| Campus-grain data absent (STAAR, staff, finance, zones) | ~4,900 | C |
| No forward-looking data (budget, forecast, tax outlook) | ~3,000 | C |
| Per-district tax-rate history absent (statewide only) | ~1,100 | C |
| Bond project detail absent (category only) | ~1,400 | C |
| Named salaries / vendor payments absent | ~1,300 | C |
| Object-level spend held but unexposed | ~1,700 | **D** |
| Outcome measures too short for a 10-year comparison | 4 | B |
| Genuinely outside scope (enrolment help, etc.) | 239 | C — correct behaviour |

---

## 8. Path to 90%

Each step below was measured by **re-running the whole simulation** with that
capability treated as present. Counting how many questions a gap "blocks"
overstates it badly — most blocked questions need two or three things, so
closing one alone converts nothing. Only re-simulation gives an honest marginal
gain.

| Step | Add | Coverage after | Gain | Kind of work |
|---:|---|---:|---:|---|
| 1 | **function_level_spend** | **75.6%** | **+7.65** | Widen a view — data already held |
| 2 | bond_projects | 77.9% | +2.30 | No statewide source; per-district |
| 3 | budget_forward | 79.7% | +1.80 | Ingest adopted budgets |
| 4 | tax_rate_history | 81.7% | +1.95 | Comptroller, partly ingested |
| 5 | campus_staar | 83.4% | +1.77 | TEA campus file |
| 6 | enrollment_forecast | 85.0% | +1.58 | Build a model — needs an error bar |
| 7 | current_year | 86.5% | +1.45 | Structural — TEA publishes late |
| 8 | conservatorship | 87.8% | +1.32 | TEA intervention list |
| 9 | vendor_contracts | 89.4% | +1.62 | No statewide publisher |
| 10 | charter_comparison | 90.6% | +1.23 | Structural |

**Verified at full sample (5 seeds, 60,042 inquiries): 90.1% full, 89.2%
business-weighted, grade A.**

Greedy selection is not proven optimal, and this report does not claim a
minimum it did not prove — it claims a path that demonstrably clears 90%.

### Tiering

**Tier 1 — do this first, alone.** `function_level_spend`. One step, +7.65
points, no new data, no new dependency. It is 40% of the entire distance to 90%
and it costs a migration.

**Tier 2 — real ingests with real value.** `campus_staar`, `tax_rate_history`,
`budget_forward`, `campus_staff`. These are where the parent audience lives, and
parents are 42% of traffic at 60.7% coverage. TAPR is already the named next
fountain in `CLAUDE.md`.

**Tier 3 — expensive, structural, or arguably out of scope.**
`vendor_contracts` and `bond_projects` have no statewide publisher — 1,200
district sources each. `enrollment_forecast` requires a model this project has
so far been right to refuse, and shipping it without an error bar would violate
the house rule that produced everything good here. `current_year` and
`charter_comparison` are structural facts about Texas, not gaps.

**An honest reading: 90% is reachable, but steps 6–10 buy coverage by adding
things the project has deliberately declined to invent.** Getting to ~85% on
steps 1–5 is engineering. The last five points are a change of editorial
policy, and should be argued on those terms rather than smuggled in as a
coverage target.

---

## 9. What it answers well (all verified against real records)

| Question | Grade |
|---|:--:|
| How much does {d} spend per student? | A |
| How much reaches the classroom? | A |
| Where does {d}'s money come from? | A |
| What do I pay to {d} on a $300,000 home? | A |
| How much of {d}'s money leaves under recapture? | A |
| How much does {d} owe, and when does it clear? | A |
| Has {d} ever passed a bond, and how did the vote split? | A |
| Is {d} putting less into the classroom than it used to? | A |
| Is {d} running a deficit? | A |
| Does {d}'s rating hide failing campuses? | A |
| Is anything unusual about {d}'s finances? | A |
| Where does this number come from? | A |

`cross_system` scores 99.2% — the highest of any category. Questions that
*combine* layers are this portal's genuine strength, which is exactly what the
architecture was built for.

## 10. What it cannot answer — the 20 that matter most

| Question | Grade | Why | What would fix it |
|---|:--:|---|---|
| How much does {d} spend on administration? | D | 14 function columns unreachable | Widen the view |
| Where can {d} cut without touching the classroom? | D | same | Widen the view |
| What does {d} spend on buses / meals / counsellors / athletics? | D | same | Widen the view |
| Which districts spend most on administration? | D | same | Widen the view |
| Is {d} wasting money? | D | flags answer part; detail unreachable | Widen the view |
| How much of {d}'s spending is people vs things? | D | object codes unexposed | Widen the view |
| What is {d}'s superintendent paid? | C | no salary data | TEA salary file |
| How much does {d} have in reserve? | C | no fund balance | TEA AFR |
| What is {d}'s budget this year? | C | actuals only, to 2025 | Ingest adopted budgets |
| Will my school taxes go up next year? | C | no forward data | Budgets + rate history |
| Why did my school tax bill go up? | C | no per-district rate history | Comptroller |
| What will I pay on MY house? | C | no appraisal roll | Out of scope (254 CADs) |
| What are STAAR scores at my child's school? | C | district grain only | TEA campus STAAR |
| How did 4th graders do in math? | C | no grade grain | TEA STAAR detail |
| How do Black and Hispanic students do? | C | only poor/EB/SpEd | Wider subgroup ingest |
| Are the teachers at my school certified? | C | no certification data | TAPR |
| Which schools lose the most teachers? | C | staff data is district-grain | TAPR |
| Which elementary would my address feed into? | C | district boundaries only | No statewide source |
| How much does {d} spend on special education? | C | PIC codes, different product | PEIMS program file |
| Is {d} under state investigation? | C | only Houston is modelled | TEA intervention list |
| What exactly did {d} build with the last bond? | C | purpose category only | No statewide source |
| Is {d} going to close schools? | C | no forecast | Demographic model |

Note how many of these are **critical-importance and parent-facing**. That is
why the business-weighted score is below the raw score.

---

## 11. AI performance — measured separately

See §2. Result recorded in `data/ai_performance_probe.json`; the probe asks the
live agent questions whose ground truth comes from the same endpoint the site
serves, so a wrong answer is an agent failure and never a data gap. Grading is
mechanical: the correct figure must appear in the answer. No model judges
another model.

---

## 12. Final assessment

```
CURRENT ANSWERABILITY:   67.1%   (95% CI 66.8–67.4, n=60,042)
BUSINESS-WEIGHTED:       64.8%
TARGET:                  90%
GAP:                     22.9 percentage points

TOP 3 BLOCKERS
  1. 14 PEIMS function-code columns are in the database and exposed
     by nothing — 8.9% of all inquiries, and the cheapest fix here.
  2. Every figure stops at the district. The largest audience (parents,
     42%) asks about a campus, and scores 60.7%.
  3. Every figure is an ACTUAL, latest fiscal 2025. Anything about now
     or next year — budgets, tax outlook, closures — cannot be answered.

MINIMUM REQUIRED CHANGES (to ~85%, all engineering)
  1. Widen v_finance_summary to the remaining 14 function columns and
     publish them per district.                              → 75.6%
  2. Bond project detail + adopted budgets.                   → 79.7%
  3. Per-district tax-rate history + campus STAAR.            → 83.4%

PROJECTED COVERAGE AFTER FULL 10-STEP PATH: 90.1% (verified, grade A)
```

**One sentence for the board:** the portal is a B+ answer to the questions its
builders asked and a D answer to the questions its visitors ask, and the single
largest correction is a view definition over data it already owns.

---

## 13. Reproducing this

```bash
python scripts/coverage_simulation.py --seeds 5 --users 1000 --inquiries 12000
python scripts/ai_performance_probe.py --n 20
```

Both write their full evidence to `data/`. Every classification in
`coverage_simulation.json` carries the exact field paths probed and the state
each returned, so any number in this report can be traced to the artefact and
district that produced it.

**Distinguishing observed from estimated, as required:**

- **Observed** — the capability map, the 188/183/5 tax population, the 16
  function columns, the two-view grant, every A/B/C/D classification. All read
  from real files.
- **Simulated** — which questions get asked, by whom, on which day, about which
  district. Monte Carlo, 5 seeds, 4 persona mixes.
- **Estimated** — every figure in §8. Those are re-simulations under the
  assumption that a named capability becomes fully available at current grain
  for all districts. Real ingests arrive with their own coverage gaps, so treat
  §8 as an upper bound.

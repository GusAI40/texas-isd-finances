# Multi-Team Audit Scorecard — July 24, 2026

Five independent audit teams (backend, data/graph science, frontend/UX,
security/ops, docs/business) scored the project 1–10 (**11 = exceptional**,
rarely awarded), plus a Monte Carlo robustness simulation
(`scripts/monte_carlo_audit.py`, seed 20260724) that stress-tested the real
system. Notably, the simulation **independently corroborated three of the
teams' headline findings** — this is not opinion, it's measured.

## Scorecard

| Dimension | Score | Weakest sub-score |
|---|---|---|
| Backend & API reliability | **7 / 11** | test-coverage 5 (DB/graph logic untested) |
| Frontend / UX / dataviz | **7 / 11** | accessibility 4 (canvas map unusable by touch/keyboard/SR) |
| Data & graph science | **6 / 11** | statistical-validity 4 (peers not truly exogenous; k=6 < k=4) |
| Security & operations | **6 / 11** | monitoring 2 (none), ci-security 4 |
| Documentation & business | **5 / 11** | funnel-viability 2, revenue-realism 3 |
| **Blended overall** | **≈ 6.2 / 11** | Good engineering, real gaps, weak business |

## Monte Carlo corroboration (measured, seed 20260724)

| Simulation | Result | Confirms team finding |
|---|---|---|
| Archetype stability (40 bootstrap re-clusters) | mean 0.70; **38.4% of districts flip archetype** (<0.6 stability) | Data team: k=6 silhouette 0.226 — weak/overlapping clusters |
| Anomaly threshold sensitivity (200 trials, ±5pp) | base 1,296 events; **±34% swing** (range 757–2,863) | Data team: 15/20/10% are knife-edge magic numbers |
| Live API coverage (50 random districts × 5 endpoints) | 0 errors on summary/peers/breakdown; **2 errors + 3 empty on /anomalies**; p50 ≈ 300ms, p95 ≈ 400ms | Backend team: reliability solid but untested edges |
| Data completeness (latest year) | enrollment/revenue/spending/instruction **0% missing**; **local_tax 15.5% missing/zero** | Data team: `fillna(0)` conflates missing with zero on `local_share` |

## Top patterns (consistent strengths)

1. **Disciplined SQL safety** — parameterized everywhere; the one dynamic
   column name goes through a hardcoded allowlist. Injection surface on the
   REST layer is effectively nil (verified live).
2. **Genuine reproducibility** — everything seeded and deterministic; edge
   lists and results committed; PCA axes sign-canonicalized.
3. **Best-in-class data storytelling & honesty** — action titles from data,
   pyramid-principle summaries, and unusually candid disclaimers ("a flag is
   a question, not an accusation"; "this is a simulation, not a survey").

## Top gaps (should exist, don't)

1. **No monitoring/alerting of any kind** — a production outage's
   mean-time-to-detect is "until a human loads the page." The product also
   silently offlines itself on the Supabase free tier after ~7 days idle.
2. **DB-backed and graph logic is untested** — the intricate turnarounds
   graph-walk (`_runs`, `src/api.py`) and every DB query have zero coverage;
   tests only exercise the no-credential 503 paths.
3. **The revenue funnel does not exist at any stage** — no analytics, no
   email capture, no accounts, no payments, no API keys. Attention → capture
   → convert is 0/0/0; you cannot even *measure* attention.

## Top blindspots (risks nobody was watching)

1. **🔴 The NLP path is not actually read-only.** `SUPABASE_DB_URL` is a
   privileged pooler role; `include_tables` limits schema *introspection*,
   not *execution*, and RLS does not bind table owners. "Only run SELECT" is
   prompt-convention only — a prompt-injected question could mutate data. The
   documented mitigation (`SUPABASE_READONLY_URL`) **does not exist** in
   `env_template.txt` — a dangling reference to a control never built.
   *(Flagged independently by the backend AND security teams.)*
2. **🔴 The `/query` rate limit is trivially bypassable.** It trusts the
   client-supplied `X-Forwarded-For` header and is per-serverless-instance —
   a rotating fake header gives unlimited paid-OpenAI calls. Combined with
   credentials still awaiting rotation, the OpenAI key is a live
   financial-abuse target.
3. **The peer benchmark's core "exogenous / non-circular" claim is only
   half true.** The similarity space includes revenue-per-student, which
   correlates 0.65 with the spending being benchmarked. Size and growth are
   exogenous; the two revenue-derived features are not.
4. **The map is 100% broken for mobile, keyboard, and screen-reader users**
   — `touch-action:none` with only mouse handlers freezes it on every phone;
   the canvas has no accessible alternative (a flat WCAG 1.1.1 + 2.1.1
   failure for a public-good civic tool).
5. **Documentation drift** — CLAUDE.md says both "24 tests" and "30 tests"
   (reality: 30); AUDIT.md still says 2008–2024; README lists 8 of 14
   endpoints; the blueprint docs (REPO_MAP/ARCHITECTURE/etc.) are stranded on
   the unmerged PR #2 branch.

## Consensus prioritized fixes (from the five "highest-value fix" votes)

1. **Dedicated read-only Postgres role for the NLP path** — converts the
   read-only guarantee from prompt convention to a DB-enforced boundary.
   *(security + backend)*
2. **Offload + time-bound the blocking `/query` call** (`run_in_threadpool` +
   `asyncio.wait_for` + `ChatOpenAI` timeout; map failure to 502 not 200) —
   removes the event-loop stall where one hung LLM request takes down the
   whole instance. *(backend)*
3. **Add touch/pointer + keyboard-accessible path to the map** — rescues two
   entire user classes. *(frontend)*
4. **Instrument reality** — privacy-friendly analytics + `/query` cost
   logging + uptime check + one email-capture box — turns an unmeasurable
   business into a testable funnel. *(business)*
5. **Re-select k by silhouette (data prefers k≈4) and drop/disclose the
   non-exogenous features; unify the 2× size weight between graph and PCA.**
   *(data science)*
6. **Reconcile doc drift** (test counts, data years, endpoint list) and merge
   or retire PR #2. *(docs)*

## Honest bottom line

This is **strong, careful engineering with a genuinely weak business case**
— roughly **6/11 overall**. The code, security-intent, reproducibility, and
storytelling are real (7s); the statistical claims are oversold and the
revenue model is aspirational bullet points on a $0 product with negative
default unit economics (every visitor costs an uncapped OpenAI call; TEA,
the Comptroller, and NCES already publish this data free). Nothing here is
fatal — every finding is addressable — but the two red-flagged security
blindspots should be closed before any promotion, and the honest move on the
business is to instrument reality rather than polish the instrument further.

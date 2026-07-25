# Engineering Log — Texas ISD Finances

Append-only session memory. **Newest entries at the top.** Written for an
engineer (human or AI) with zero prior context. Maintained by the `/ariba`
skill — see `.claude/skills/ariba/SKILL.md`. Never put secrets here.

Entry template:

```
## YYYY-MM-DD — <one-line headline>
**What changed:** facts — files, deployments, data.
**Why:** the reasoning git can't record.
**Gotchas:** anything that cost real time to figure out.
**Open items:** carried forward + new.
**Notes:** (quick /ariba note additions land here)
```

---

## 2026-07-25 — Phones can use the map; portal renamed "Texas ISD Financial Resource Guide"

**What changed:** Two shipped pieces, both deployed and verified live.

(a) `static/map.html` — full touch support. Added `touchstart` /
`touchmove` / `touchend` handlers: one-finger drag pans, two-finger pinch
zooms (clamped `k` to 1–14), a tap that doesn't drag opens the district.
Moved `touch-action:none` off `.mapwrap` and onto `canvas` alone so the
page still scrolls normally around the map. `resize()` now uses a portrait
aspect on narrow screens (`h = w * 1.05` under 560px, `w * 0.62` above) —
a 16:10 letterbox on a phone was ~120px tall. Added a `.mobonly` gesture
hint line.

(b) `static/index.html` — Resource Guide framing. Brand renamed to
"Texas ISD Financial Resource Guide" (subtitle: official TEA data ·
fiscal 2009–2025 · 1,202 districts); intro rewritten to name every
audience by name. New **Methods & citation** section with four
collapsible blocks: where the data comes from (loaded unchanged from TEA
— no estimating, no modeling), how each number is calculated (per-student
divisor, why our total exceeds the nationally-quoted per-pupil figure,
the exact TEA function codes behind each category, why peer matching
excludes spending, what each flag threshold means), known limits — read
before citing, and a copy-paste citation with retrieval date.

**Why:** User: "then fix it! I want this to become the Texas ISD Financial
Resource Guide where it becomes such a resource guide that it starts to be
used for decisions to develop new policies." Two things blocked that. The
map was 100% non-functional on phones — no touch handlers at all, so the
audience most likely to arrive from a social link (parents, boosters) hit
a dead screen. And nobody cites a source that won't show its work: a
policy-grade reference has to state its provenance, its arithmetic, and
its limits in the same breath as its numbers.

**Gotchas:**
- `touch-action:none` on the wrapper killed page scroll around the map —
  it must be scoped to the canvas element only.
- Mouse and touch handlers both fire on hybrid devices; the touch path
  tracks its own `touchStart` state and calls `preventDefault()` inside a
  `{ passive:false }` listener, which is required or Chrome ignores it.
- The "known limits" block is deliberately blunt (no HVAC/technology
  isolation possible, fiscal-year timing differences, overlapping
  categories, the AI answer box can be wrong). Underselling here is the
  only thing that makes the rest citable.

**Open items:** unchanged plus map keyboard/screen-reader path (canvas has
no SR alternative; search-based access exists). Still open: credential
rotation (user-side, 🔴), dedicated read-only DB role for the NLP path,
`/query` needs `run_in_threadpool` + `asyncio.wait_for` (today it blocks
the event loop and can 200 on failure), real rate limiting
(X-Forwarded-For is spoofable), privacy-friendly analytics, DB keep-alive
against the Supabase free-tier 7-day idle pause, insight percentile/rank
context, PR #2 (`docs/complete-repo-blueprint`) awaiting user review —
do not merge.

---

## 2026-07-24 — Map rewritten for humans (landmarks, neighborhoods, plain axes)

**What changed:** `static/map.html` reframed from an analyst scatter into
"A seating chart for every school district in Texas." Added: plain-English
"What am I looking at?" explainer; NEIGHBORHOOD labels (the 6 archetype
clusters named in place on the canvas); LANDMARK labels (14 largest
districts, spread-filtered to avoid collisions) so the picture has
recognizable anchors; plain axis labels drawn on canvas ("smaller
districts ← → bigger", "shrinking ←→ growing"); search now finds/zooms/
pins a district on Enter and writes a full-sentence readout naming its
section, size, spending vs neighbors, and closest matches; legend in human
words. 32 tests green; deployed + verified live.

**Why:** User looked at the map and said "I can't decipher this... would a
mom understand?" Correct — it was 1,202 anonymous dots with PCA jargon
axes. A real map has landmarks; ours had none. This was the one screen
that failed the universal-comprehension test.

**Gotchas:** Neighborhood labels are suppressed while a district is
focused (otherwise they fight the ego-network). Landmark labels are
skipped in "Flagged only" mode and drawn with white backing rects for
legibility over dots. Landmark spread filter uses data-space distance
>0.55 so labels don't stack in the dense big-district corner.

**Open items:** unchanged — launch-hardening (rate limit, RO DB role, map
TOUCH support + keyboard a11y still outstanding, analytics), rotate creds,
PR #2 review, operating-vs-total per-student KPI labeling.

---

## 2026-07-24 — "The dollar" + audience lenses + AI disclosure + TAG contact (live)

**What changed:** (1) AI disclosure + data disclaimer + Technology
Automation Group / TAG ai contact (839-888-2424, ubntag.com) in the footer
of BOTH portal pages (index.html, map.html). (2) "Your dollar" hero: total
district spending rendered as 100 colored pennies by category, with a
computed headline ("Of every dollar X spends, N cents goes to classroom
teaching"). (3) Six audience lenses (parent / taxpayer-grandparent /
booster / business / press / admin) that re-narrate the SAME numbers for
the reader; choice persists in localStorage. (4) One-tap 1200x630
shareable social PNG with penny grid + TAG branding. 32 tests green,
deployed, verified live on both pages.

**Why:** User asked for a Steve Jobs "touch of magic" and universal
comprehension (single mother, 81-year-old grandad, superintendent, coach,
booster, press). The Jobs move is making the abstract concrete: pennies
are a unit everyone owns. Lenses solve "one dashboard can't speak to
everyone" without forking the data — same honest numbers, different
narration.

**Gotchas:** Pennies use LARGEST-REMAINDER rounding so they always sum to
exactly 100 (naive rounding gives 99 or 101). The dollar is of TOTAL
spending (not operating) deliberately — it visually explains why
per-student totals look high (Dallas FY2025: 33c classroom, 23c
construction, 15c debt). renderExec was slimmed to delegate to
lensStory(); dead locals removed.

**Open items:** unchanged — launch-hardening (real rate limit, RO DB role,
map touch/a11y, analytics), rotate creds, PR #2 review, operating-vs-total
per-student labeling on the KPI tile.

---

## 2026-07-24 — Actionable-intelligence engine live (peer-benchmarked $ findings)

**What changed:** New `GET /district/{id}/insights` + top-of-dashboard
"Actionable Intelligence" section. For each district it compares
operating/instruction/admin/facilities/debt per student and payroll/
contracted share against its SIMILARITY-GRAPH peers, fires only material
deviations (>20% AND >$100k/yr), quantifies each in $/year, ranks by
magnitude, returns top 6. Dashboard renders ranked cards ("<metric>: X%
above peers · $Y/year above peers") colored concern-vs-strength, framed as
review targets not verdicts. 32 tests green. Deployed + verified live:
Dallas debt 34% above = $128M/yr, admin 44% = $71.5M/yr; Houston admin 89%
= $181M/yr; San Antonio 4 findings.

**Why:** User asked for "actionable intelligence." This turns raw numbers
into decisions and is the app's most defensible feature — it leans on the
exogenous peer graph (the unique asset) to say "where you differ from
districts genuinely like you, in dollars."

**Gotchas:** admin = fct21+fct23+fct41_92 combined; large-district
deviations can be big and real but the copy hedges ("questions, not
verdicts"). Materiality floor (20% AND $100k) keeps tiny districts from
spamming findings; needs >=4 peers with data or returns empty. Endpoint
joins 3 views + district_similarity per request — fast enough (p95 <500ms).

**Open items:** unchanged — labeling fix (operating vs total per-student),
launch-hardening (rate limit, RO role, map a11y, analytics), rotate creds,
PR #2. Next data candidates researched: Urban Institute API (#1),
USAC E-rate (#2) — see prior turn; not yet ingested.

---

## 2026-07-24 — Tier-1 data enrichment (object + program dimensions) live + data roadmap

**What changed:** Surfaced two spending dimensions the summarized data
already carried but the dashboard never showed. New `v_spending_detail`
view (`sql/create_detail_view.sql`), `GET /district/{id}/spending-detail`,
two dashboard sections (object: payroll/contracted/supplies/other —
sums to operating total, 100% populated; program: regular/special-ed/
compensatory/bilingual/career-tech/gifted/athletics — 89-100%). Shared
`barChart()` renderer. `docs/DATA_ROADMAP.md` scopes Tier-2 (detailed
PEIMS function×object) and Tier-3 (vendor/check-register pilot — the only
path to real HVAC/technology numbers). 31 tests green; deployed + verified
(Dallas: 81% payroll, 12.3% special-ed).

**Why:** User asked whether HVAC/technology are inferable. Answer: no — the
summarized data's granularity ceiling is function+object+program, never a
named HVAC or total-tech line. Delivered the max the loaded data allows
(object+program) and documented the data layers needed to go deeper.

**Gotchas:** HVAC lives inside function 51 (plant maintenance & ops, also
utilities/custodial/repairs) — not separable without vendor data.
"Technology" is smeared across fct53 (IT-ops only), instruction devices,
capital, and E-rate — no single line. Program % overlaps object % (a
special-ed salary is both) — dashboard caption says so explicitly to avoid
double-count confusion. Rerun nothing extra; view is over base table.

**Open items:** unchanged — labeling fix (operating vs total per-student)
still recommended; launch-hardening list (rate limit, RO role, map a11y,
analytics); rotate creds; PR #2 review.

---

## 2026-07-24 — Multi-team audit + Monte Carlo robustness sim (scorecard)

**What changed:** Ran 5 parallel audit-team subagents (backend, data/graph
science, frontend/UX, security/ops, docs/business) + a quantitative Monte
Carlo (`scripts/monte_carlo_audit.py`, seed 20260724). Results in
`docs/AUDIT_SCORECARD.md` + `docs/monte_carlo_audit.json`. Scores (1-11):
backend 7, frontend 7, data-science 6, security 6, docs/business 5;
blended ~6.2.

**Why:** User asked to identify patterns/gaps/blindspots and score
everything with parallel teams. No fixes applied yet — this is assessment.

**Key findings (verified, not opinion):**
- 🔴 SECURITY: NLP path uses the privileged pooler role; RLS doesn't bind
  owners and include_tables only limits reflection → "read-only" is
  prompt-convention only, prompt-injection could mutate data. Documented
  mitigation SUPABASE_READONLY_URL does NOT exist in env_template.txt.
- 🔴 /query rate limit trusts spoofable X-Forwarded-For + per-instance →
  uncapped paid-OpenAI abuse (compounds unrotated-key item).
- MC corroborated: 38.4% archetype instability (k=6 silhouette 0.226 <
  k=4's 0.290); anomaly thresholds swing ±34% under ±5pp; local_tax 15.5%
  missing conflated by fillna(0); peers include rev/student (corr 0.65
  with spend) so "exogenous" claim is half-true.
- FRONTEND: map 100% broken on touch + keyboard + screen-reader (WCAG
  1.1.1/2.1.1 fail).
- DOC DRIFT (confirmed): CLAUDE.md says both 24 and 30 tests (real: 30);
  AUDIT.md still says 2008-2024; README lists 8 of 14 endpoints; blueprint
  docs (REPO_MAP etc.) stranded on unmerged PR #2 branch.

**Open items:** the 6 prioritized fixes in AUDIT_SCORECARD.md (top: RO DB
role for NLP; threadpool+timeout /query; map touch/a11y; instrument
analytics; re-select k; reconcile doc drift). Plus standing: rotate creds,
review PR #2. None applied yet — awaiting go.

---

## 2026-07-24 — 10x graph polish v2: archetypes + typicality centrality (live)

**What changed:** `scripts/graph_insights.py` now clusters districts into
6 archetypes (deterministic k-means, seed 0, on z-scored exogenous
features; named from median stats) and computes typicality = in-degree
centrality in the directed k-NN graph (0-100 percentile). Emitted per
node as `c`/`t` plus archetype metadata in `static/map_data.json`. Map
gains a "Color: spending / Color: archetype" toggle with a counted named
legend, and the selection panel shows archetype + typicality. Deployed +
verified live (6 archetypes, typicality spans 0-100).

**Why:** "Polish 10x" — the map positioned nodes but never revealed the
graph's structure. Archetypes turn 1,202 dots into a labeled taxonomy of
Texas district types; in-degree centrality gives a genuine "how typical
is this district" score (archetype vs structural outlier), distinct from
size.

**Gotchas:** k-means over-fragments if done as label-propagation
communities on mutual-kNN (got 31); k=6 k-means on the embedding is the
right grain for a *labeled* taxonomy. Archetype names come from median
enrollment/growth/local-share (interpretable, stable) not z-score
thresholds (which lumped everything "Mid-size"). Rerun graph_insights.py
after each TEA refresh.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-24 — 10x polish: interactive similarity map (edges, ego networks, zoom)

**What changed:** Rewrote `static/map.html` into a real graph
visualization. `scripts/graph_insights.py` now emits per-node neighbor
indices (top-6 from the committed edge list), canonicalized + bipolar-
labeled PCA axes, and a recent-flag layer into `static/map_data.json`.
Map features: ego-network edges drawn on hover/pin, click-to-pin
selection panel with clickable re-centering neighbor list, zoom
(scroll/pinch) + pan (drag), devicePixelRatio-aware retina rendering,
dollar-valued quintile legend, "Flagged only" layer (183 districts),
deep-link `/map?d=<district>`, dashboard button deep-links to current
district. 30 tests green; deployed + verified live.

**Why:** "Polish 10x" on the graph work. Prior map was a plain scatter
that hid the graph's edges, was blurry on high-DPI, and had unlabeled
axes (wasting PCA's interpretability). Axes now read as Texas-finance
spectrums: "leaner-funded ↔ bigger", "state-funded ↔ growing".

**Gotchas:** PCA sign is arbitrary — canonicalized (fix log_enroll
loading positive on PC1, growth5 positive on PC2) so the layout is
stable across rebuilds. Deploy payload must include static/map.html +
static/map_data.json. Rerun graph_insights.py after each TEA refresh.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-24 — Graph insight suite live: turnarounds, statewide map, co-occurrence

**What changed:** `scripts/graph_insights.py` (deterministic) produces:
PCA similarity-map coordinates (`static/map_data.json`, PC1+PC2 = 70%
variance), flag co-occurrence analysis, and temporal drift. New routes:
`/map` (explorable canvas map of all 1,202 districts — hover, search
highlight, click-through), `/map-data`, and
`GET /district/{id}/turnarounds` (graph walk finding peers that reversed
>=2-year deficits or >=3-year enrollment slides). Dashboard shows a
"Proof it's doable" section when peers have turnarounds, plus a State map
header link. Findings in `docs/GRAPH_INSIGHTS.md`. 30 tests green.
Deployed + verified live, including positive turnaround hits (South San
Antonio ISD enrollment reversal; Centerville ISD deficit reversal).

**Why:** Graph-lens roadmap items user approved with "Do it". Headline
analytical finding: revenue_drop + enrollment_decline co-occur at 6.1x
lift — enrollment decline is the leading indicator of fiscal stress.
Temporal drift shipped as analysis only (top movers are small-district
volatility; needs size-weighting to be a feature) — honest scope call.

**Gotchas:** Deploy payload must now include static/map.html and
static/map_data.json. Rerun graph_insights.py + build_similarity_graph.py
after each TEA refresh.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-23 — Peer comparison upgraded to a district similarity graph (live)

**What changed:** New k-NN similarity graph (1,202 nodes, k=12, 14,424
edges) built by `scripts/build_similarity_graph.py`; edges committed at
`docs/similarity_edges.csv` and loaded into new `district_similarity`
table (`sql/create_similarity_table.sql`). `GET /district/{id}/peers` now
walks the graph (fallback: enrollment window; response has `basis`
field). Deployed + verified live: Dallas peers = Houston, Austin,
Northside, Frisco, Plano.

**Why (the graph-engineering insight):** peers must be matched on
EXOGENOUS features (log enrollment, 5-yr growth, revenue/student,
local-tax share) — never on outcome metrics like spending, or the
benchmark becomes circular ("districts that spend like you spend like
you"). Enrollment-only matching missed funding structure; the graph
captures it.

**Gotchas:** rebuild + reload the graph after each annual TEA refresh
(documented in script + SQL comments). PostgREST upsert used
`Prefer: resolution=merge-duplicates` so reloads are idempotent.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-23 — PR #1 merged to master

**What changed:** Merged PR #1 (all audit + launch + dashboard work) into
`master` with a merge commit to preserve the commit history. Work branch
restarts from master per protocol.

**Why:** master previously showed pre-audit code to repo visitors.

**Open items:** credential rotation (user-side) remains the only red item.

---

## 2026-07-23 — A+ pass: all report-card gaps closed; white-minimalist McKinsey/SWD redesign live

**What changed:** New `v_spending_breakdown` view (TEA function codes → 9
MECE categories) + `GET /district/{id}/breakdown`; anomaly cards show
before/after numbers; side-by-side district compare (orange series); PNG +
CSV export on every chart; per-section TEA citations; enrollment
multi-year-decline callout; in-app rate limit on /query (10/min/IP,
QUERY_RATE_LIMIT env). UI v3: pure white minimalism, McKinsey action
titles computed live from data, auto-generated executive summary (pyramid
principle), SWD gray-context/blue-focus charts, direct end labels, tables
behind disclosure toggles. 29 tests green. Deployed and verified live
(Dallas breakdown: 55% classroom instruction).

**Why:** User asked for A+ vs the demand-weighted report card and a
McKinsey/storytelling-with-data white design. Demand-weighted grade moved
≈3.5 → ≈3.96/4.0.

**Gotchas:** Rate limiter is per-serverless-instance (documented in code) —
CDN/WAF still recommended for a hard global cap. Light-only theme is a
deliberate user-pinned choice (white background), replacing the earlier
dark-mode support.

**Open items:** rotation + PR #1 merge still user-side; those two are what
separates product A from A+.

**Notes:**

---

## 2026-07-23 — Dashboard redesign driven by Monte Carlo user simulation; deployed live

**What changed:** Simulated 1,000 Texas school admins against the real
district population (`scripts/simulate_admin_usage.py`, seed 42 —
reproducible; results in `docs/simulation_results.json`). Findings drove a
full UI rebuild (`static/index.html`): KPI tiles with plain-English
captions, trend chart vs statewide median with metric tabs, similar-size
peer comparison, spending breakdown, per-district anomaly explainer cards,
guided first-run tutorial, disclaimer modal/footer, print + CSV export.
New endpoints: `GET /district/{id}/peers`, `GET /benchmarks`,
`district_number` filter on `/anomalies` (SQL validated on live DB via
management API before shipping). Docs: `docs/UX_RESEARCH.md`,
`docs/TUTORIAL.md`. 27 tests green. Deployed to Vercel production and
verified live (peers for Dallas: Cy-Fair/Houston/Northside/Katy, 70th
percentile, 2025 statewide median $19,314/student).

**Why:** User mandate: build what admins want, not what we want. The
simulation showed the old UI led with the LOWEST-demand feature (freeform
NLP, 2.3%) and had zero support for the top four demands (peer comparison
16.1%, trends 13.8%, board-ready output 11.5%, statewide context 10.6%).
Page order now mirrors the demand ranking.

**Gotchas:**
- Deploys still go through the Vercel REST API with the user-supplied PAT
  (re-staged temporarily from conversation, shredded after). Deploy payload
  swaps `requirements-vercel.txt` in as requirements.txt (comments
  stripped).
- Persona/task priors are modeled assumptions, documented honestly in
  UX_RESEARCH.md — replace with real analytics/interviews when available.

**Open items:** unchanged (rotation, rate limit, PR #1 merge) — see
CLAUDE.md status.

**Notes:**

---

## 2026-07-22 — Memory system created (/ariba skill, CLAUDE.md, this log)

**What changed:** Added `.claude/skills/ariba/SKILL.md` (catch-up / save /
note modes), `CLAUDE.md` boot file, and this log, seeded with the project's
full history below. All committed to `claude/audit-public-launch-ocd7ra`.

**Why:** Agent sessions are ephemeral containers with zero memory. The repo
is the only durable store, so project memory must be committed files that
every future session auto-loads (CLAUDE.md) or is instructed to read
(/ariba). Design principle: log decisions WITH rationale, verify live state
before trusting notes, never store secrets.

**Open items:** see Current Status block in CLAUDE.md.

**Notes:**

---

## 2026-07-22 — WENT LIVE: Supabase provisioned, TEA data loaded, Vercel production deploy, PR #1 opened

**What changed:**
- Created Supabase project `texas-isd-finances` (ref `zwhvabkvrexphlskubog`,
  us-east-1, org "GOAT-UIX") via Management API using the user's PAT.
- Downloaded TEA's current "Summarized PEIMS Actual Financial Data" release
  directly from tea.texas.gov (`/media/423296`, ~19 MB, sheet `DATAMART`) —
  fresher than the project ever had: fiscal 2009–2025.
- Ran `scripts/prepare_data.py` → 20,587 rows × 140 cols; loaded via
  PostgREST in 1,000-row batches (direct Postgres is blocked in the dev
  container — HTTPS only); applied `sql/create_tables.sql` via Management
  API query endpoint.
- Deployed to Vercel (project `texas-isd-finances`, account `tag-ai`) with
  env vars `SUPABASE_DB_URL` (transaction pooler, port 6543) and
  `OPENAI_API_KEY`. Live: https://texas-isd-finances.vercel.app
- Opened PR #1 (audit branch → master).
- Shredded all locally staged credentials after deploy.

**Why key decisions went the way they did:**
- Transaction pooler (6543) for serverless; asyncpg needs
  `statement_cache_size=0` with it (added in `src/api.py`).
- Vercel deploy uses `requirements-vercel.txt` (full API incl. NLP, minus
  pandas/matplotlib/etc.) to stay under the 500 MB bundle cap. NLP works in
  production — verified with a real Dallas ISD question.
- Restructured `sql/create_tables.sql` to run AFTER import: the old static
  CREATE TABLE defined only 21 of 140 real columns, so the documented
  schema-first order could never import.

**Gotchas (each cost real time — don't rediscover):**
- Live testing caught bugs static review missed: (1) pandas re-reading the
  clean CSV stripped leading zeros from district IDs — fixed in DB with
  `LPAD(...,6,'0')` and in `import_to_supabase.py` with
  `dtype={"district_number": str}`; (2) `/anomalies?year=X` returned
  unflagged rows — flag condition now always applied; (3) the real TEA
  column is `all_funds_instruction_transfer_expend_fct11_95`, not the
  invented `all_funds_instruction_expend`.
- The dev container cannot open raw TCP to Postgres; use Supabase
  Management API (`POST /v1/projects/{ref}/database/query`) for SQL and
  PostgREST (service_role key, `Prefer: return=minimal`) for bulk inserts.

**Open items:** credential rotation (user-side), `/query` rate limit,
merge PR #1, Supabase free-tier idle-pause watch.

---

## 2026-07-22 — Audit round 2: everything validated against current provider docs

**What changed:** Rewrote `src/nlp_engine.py` on LangChain 1.x
`create_agent` (pinned `langchain>=1.0,<2.0`); fixed `env_template.txt` to
lead with the Supabase session-pooler string; fixed `vercel.json`
(`excludeFiles`, not the unsupported `includeFiles`); removed dead Pydantic
models; added `tests/test_nlp_engine.py` (constructs the real agent against
SQLite so LangChain API drift fails CI); added `PROJECT_MAP.md`.

**Why:** User mandate: assume nothing, validate every assumption against
current docs. It paid off — three latent production-killers found.

**Gotchas:**
- `create_sql_agent` no longer exists in langchain 1.x — `/query` was dead
  on any fresh install and round-1 tests had masked it by not importing the
  module. Lesson: every module needs at least an import/construction test.
- Supabase direct host (`db.<ref>.supabase.co`) is IPv6-only without a paid
  add-on; Render/Railway/Vercel egress IPv4 → always use the pooler.
- `langchain-community` sunset June 2026 (still works; watch issue #674).
- SQLite dialect lacks materialized-view reflection → NLP engine takes an
  injected `SQLDatabase` in tests; Postgres path uses `view_support=True`.
- Git-history secret scan: no full secrets, but old Supabase project ref
  `emtwbizmorqwhboebgzw` visible in deleted internal docs → rotate that
  project's creds if still live.

---

## 2026-06-01 → 2026-07-19 — Audit round 1 and launch prep (branch created)

**What changed:** On branch `claude/audit-public-launch-ocd7ra`: fixed
broken relative import (app could never boot via documented command); made
NLP engine lazy so the app boots without credentials (data endpoints 503
cleanly, /health reports "degraded"); fixed CORS (wildcard+credentials
invalid), Plotly `update_xaxes`/`update_yaxes`, scatter trendline, SQL
column interpolation; enabled the RLS the README promised; migrated to
lifespan handler. Added `static/index.html` public portal, pytest suite,
enforcing CI, `Dockerfile`, `render.yaml`, `api/index.py`, `DEPLOYMENT.md`,
`AUDIT.md`. Earlier commits (pre-audit) sanitized credentials and added
LICENSE/CONTRIBUTING/SECURITY.

**Why:** Repo was a prototype: nothing had ever actually run end-to-end.
Goal was public-launch readiness with graceful degradation so deploy could
precede credential wiring.

**Gotchas:** CI previously used `ruff --exit-zero` (never fails) and a
"type check" that only printed a version — green CI proved nothing.

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

## 2026-07-26 — Audit: the AI was stating falsehoods, and nothing was findable

**Graded the whole system, then fixed the two failing areas.** Data work
graded A; **AI accuracy D, distribution D.**

🔴 **The answer box was confidently wrong.** Asked "how many districts are
in the data" it replied *"There are a total of 100 distinct school
districts."* Truth: 1,310. Asked again in other words: 1,310, correct.
**Non-deterministic, which is worse — you cannot warn users precisely.**

**Cause was our own system prompt**, which said "Limit results to prevent
overload (default LIMIT 100)". The agent put `LIMIT 100` on a
`SELECT DISTINCT` and reported the row count as the total. Replaced with an
explicit *counting is not limiting* rule (never LIMIT an aggregate; use
`COUNT(DISTINCT …)`; never present returned-row-count as a total; flag
possibly-truncated listings) plus the ground truth (1,310 / 20,587 /
2009–2025) so a contradicting answer is caught before a reader sees it.
**Verified fixed: same question 5× on production, 1,310 every time.**

**Distribution (why nobody had found it):**
- **Shared links now work.** `/?d=043905` opens that district on a device
  that has never seen the site. Before this, every link posted anywhere
  opened on the *reader's own* saved district — it would have silently
  broken an entire campaign.
- `og:`/`twitter:` tags on report and map; shares were bare blue links.
- `robots.txt` + sitemap of all 1,205 district pages (district views render
  client-side from `?d=`, so crawlers had no way in). `/query` disallowed —
  no crawl budget on the paid path.
- Vercel Web Analytics (no cookies). We had zero usage visibility.
- **txisd.dev** swept through pages, docs and citations, replacing the
  vercel.app prototype URL. *That domain existed the whole time and was in
  neither CLAUDE.md nor this log* — every link handed over for days pointed
  at the prototype. **Custom domains belong in the boot file.**

**Gotchas:**
- **`/districts?limit=500` returns the first 500 ALPHABETICALLY.** The first
  shared-link implementation looked names up there: worked for Frisco (F),
  silently failed for Pittsburg (P) and ~800 others, which announced
  themselves as "032902". Now resolved from the `summary` payload
  `loadDashboard()` already fetches. **A limit is a filter — testing one case
  inside it proves nothing about cases outside it.**
- Local harness passed; production caught it. Test across the *range*, not
  one sample.

**Still open (graded, not fixed):** map keyboard/screen-reader path (C−),
`/query` threadpool + timeout, read-only DB role, spoofable rate limit,
no CSP/X-Frame headers, 518 KB geomap payload on mobile.

**Intel still missing, ranked:** revenue composition (24 unused columns —
answers "who pays", needs no new data) · General Fund vs All Funds (67 unused
pairs) · campus-level TAPR (parents attend schools, not districts) · teacher
salary by experience band (likely the mechanism behind the turnover finding)
· bond schedules · multi-year turnover averages · vendor registers.

---

## 2026-07-26 — "One child": the report at human scale

**What changed:** A card at the top of the outcomes section that divides the
same figures down to one student, one classroom, one childhood. Plus
`border_keeps_teachers_better` in `scripts/build_outcomes_data.py`.

**The three beats:**
- **"$163 a day"** — spending per student over a 180-day year. Billions move
  nobody; a daily figure for one child does.
- **"2 of 10 teachers"** — of ten teachers present when a child starts
  kindergarten, how many would still be there when they leave fifth grade at
  today's turnover rate, beside the same figure for similar districts.
  **Nobody has ever handed a parent that number.**
- **"6 of 10 classmates"** — student poverty as a classroom, not a percentage.

Then the closer: the bordering district teaching similar students that keeps
its teachers. Rockport-Fulton loses 30.4%; Calhoun County next door, 66.5%
student poverty vs 60.9%, loses 10.7%.

**Gotchas:**
- The ten-teacher figure compounds `(1 - turnover)^5`. That **overstates**
  churn among veterans, because leavers skew new. The caveat is **in the
  card, not a footnote** — stating it is what makes the number quotable
  instead of attackable. Do not remove it to tighten the layout.
- `border_keeps_teachers_better` uses TIGER adjacency (shared boundary
  vertices), similar poverty within 8 pts, turnover better by >=4 pts.
  **373 of 1,205** districts have one. Needs `--shapefile` on the outcomes
  build; without it the field is simply absent and the card degrades.
- Rebuild order still matters: `build_outcomes_data.py --shapefile ...` then
  `build_district_geo.py` (which merges the measures).
- When spot-checking a district in the browser, **use a real district number** —
  the page trusts the number for data and the stored name for display, so an
  invented pair renders the wrong name against real figures. Cost me one
  confusing test.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted 2026-07-25.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, keyboard/SR path for
both maps, PR #2 review.

---

## 2026-07-26 — Named the report, surfaced the map, credited the collaboration

**What changed:** Three things, all live.

1. **The map was live but unfindable.** "Map of Texas" sat in a row of quiet
   text links beside Print; the owner shipped it and could not find it. It is
   now the one filled button in the header. **Shipping and surfacing are
   different jobs** — doing the first is not doing the second.
2. **Named the work.** Hero eyebrow: "Storytelling with data · a story of
   Texas ISD", plus a credential band — 17 years of state records, 1,310
   districts, 20,587 financial records, the annual total, "every number
   traceable to the State of Texas". **Every figure reads from live data at
   load**, so it cannot drift when TEA publishes again. First pass got this
   wrong twice: hardcoded a record count, and fetched the 518 KB boundary
   file on the landing page purely to count districts. Both removed.
3. **Collaboration credit** — TAG ai with Michelle Sanchez, Realtor,
   Coldwell Banker Realty.

**Gotchas / judgement calls on the credit:**
- Her details came from the `michelle-sanchez-brand` skill, not from chat.
  Correct form is **"Realtor | Coldwell Banker Realty"** (not "Coldwell
  Banker Realtor"), and **TREC License #0724260** is included because Texas
  license holders' public-facing material should carry it.
- **No unverifiable claims.** The copy states the shared goal that was given;
  it invents no client anecdote.
- **Added an independence statement unprompted.** A school-data guide
  credited to a realtor invites the question "are these numbers picked to
  sell houses?" Silence leaves it open. Stating that figures are TEA's
  loaded unchanged, that nothing is ranked or recommended, and that no party
  influenced any number or method, closes it. Disclosure is what makes the
  collaboration an asset.
- **Deliberately did NOT apply her brand chrome** (black header bar, gold
  accents, CB badge, headshot). Correct for a listing presentation; in a
  public data report it would read as real estate marketing and spend the
  exact credibility this report cannot afford. The report keeps its
  white-minimalist design. Revisit only if she wants a co-branded PDF, which
  is a different artifact.

**Positioning settled** (for future sessions): TAG ai's angle is *nobody
trusts a capability deck, everybody trusts a thing they already used.* The
guide is the demonstration; the footer credit is enough. Leading with TAG
turns it into vendor content districts will not cite in a board meeting.

**Open items:** 🔴 **rotate the Vercel / Supabase / GitHub PATs pasted
2026-07-25** — still outstanding, the Vercel one deploys to production.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, keyboard/SR path for
both maps, PR #2 review. Product idea with the strongest case: the
one-paragraph plain-English verdict-free "should I worry?" sentence,
generated for all 1,205 districts — it serves parents, teachers, taxpayers
and reporters at once.

---

## 2026-07-26 — The real map of Texas is live (and it needed no Mapbox)

**What changed:** `/geomap` — 1,005 actual school-district boundaries,
colourable by teacher turnover, spending, student poverty, or how far a
district beats what its demographics predict. Plus
`scripts/build_district_geo.py`, `scripts/simulate_map_value.py`,
`docs/MAP_VALUE_SIMULATION.md`, and routes `/geomap` + `/district-geo`.

**Asked before building.** The Monte Carlo (100k visitors placed by real
enrolment, adjacency from 2,863 real shared borders) had to be able to say
"no". It said: **100%** of visitors see a bordering district that is not
among their statistical peers; **64.7%** share no overlap at all; median
overlap between neighbours and k-NN peers is **0**. The map is a different
question, not a prettier answer.

**No Mapbox, on purpose.** Polygons are Census TIGER 2024 (public domain),
the renderer is our own canvas code, and "find my district" is
point-in-polygon **in the browser** — location never leaves the device, no
API key, no per-load billing, nothing to lock into. Mapbox remains optional
later for street-address geocoding and a basemap; neither is needed here.
Free tier if we ever do: 50k map loads and 100k geocodes a month.

**Gotchas:**
- Census keys on NCES codes, we key on TEA numbers. **Join by normalised
  name: 1,005 of 1,006.** The ten mismatches are an explicit alias table
  checked by hand (`Ft Davis` vs `Fort Davis`, `Hamlin Collegiate`,
  `LaPoynor`…). `Spring Creek ISD` is genuinely absent from TEA 2024 — left
  unmatched rather than forced.
- **Douglas-Peucker must be iterative here.** Texas rings run to tens of
  thousands of vertices; the recursive form blows the stack.
- 27 MB shapefile → **518 KB**: quantise to 1e-4 deg (~11 m), delta-encode
  along each ring, drop sub-threshold islands. 1,660,525 vertices → 48,760
  (2.9%). Measures are merged into the same file so the map is one fetch.
- **Charters have no boundary** — the map covers ~92% of Texas students and
  says so on its face. Never let a map imply those children do not exist.
- Rebuild after any TEA release: `build_outcomes_data.py` first (its output
  is merged in), then `build_district_geo.py`.

**What it shows.** Coloured by turnover, Texas renders as a **patchwork, not
regions** — the visual form of the finding that neighbouring districts differ
in turnover 87% as much as random ones, while salary (a labour-market
quantity) is only 63%. Pin Wharton ISD and the page says it plainly: loses
33% of its teachers; El Campo next door, 73.8% vs 78.1% student poverty,
loses 12.7%.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted 2026-07-25.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, keyboard/SR path for
both maps, PR #2 review.

---

## 2026-07-26 — Live-figures ticker, and the hero flash (a real bug) fixed

**What changed:** A scrolling ticker under the header, and the end of the
"hero appears then vanishes" flash a user reported.

🔴 **The flash was worse than it looked.** `boot()` did
`await loadStatewide()` **before** reading `localStorage` for a saved
district, so a returning visitor saw the entire hero — headline, subtitle,
statewide penny grid — for the length of two API round-trips, then watched
it disappear when `.compact` was applied. Anything that appears and then
vanishes reads as broken.

**Fix — do it before first paint, never in `boot()`:** a tiny inline script
in `<head>` sets `html.has-district` from `localStorage`, and CSS keyed off
that class hides the hero from frame one. The `Find your district` /
`Look up a different district` label swap moved out of JS into the same
class for the same reason. The statewide fetch no longer blocks the district
load. Verified by sampling the DOM 16 times during load against
**production**: hero visible in **0 frames** for a returning visitor, and
still renders for a first-timer.

**Ticker:** built only from figures already computed on the page —
statewide total and penny split, median teacher turnover and salary, the
lever finding, and once a district is open its per-student spending, largest
peer gap in real dollars, score vs prediction, and turnover vs peers. If a
figure can't be computed the item is omitted; nothing is padded and no
number is editorialised into a headline. Pace scales with content length
(~71s live), pauses on hover/focus, drops animation under
`prefers-reduced-motion`, hidden in print, no horizontal overflow on a
390px phone.

**Gotchas:**
- **Anything that depends on `localStorage` for above-the-fold layout must
  be applied pre-paint**, via `<head>` + a class on `documentElement`. Doing
  it in `boot()` guarantees a flash, and the flash lasts as long as whatever
  `boot()` awaits first.
- The ticker track is rendered **twice** and animates to `translateX(-50%)`
  — that is what makes the loop seamless. Don't "optimise" the duplicate
  away.
- **Hiding the hero also hid the statewide penny grid**, which lived only
  there — returning visitors lost the best explanation of the whole site.
  It now renders in **Statewide context** as well (one definition, two
  containers, `['', '-2']`). Watch for this whenever the hero changes.
- The pre-paint rule was written as `html.has-district .hero-fig`, which
  matched **any** `.hero-fig` on the page and silently gave the new
  statewide copy zero height while all 100 pennies sat in the DOM. Scoped to
  `.hero` descendants. A selector written for one element can reach an
  element that doesn't exist yet.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted 2026-07-25.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, map keyboard/SR path,
outcomes lens on the state map, PR #2 review.

---

## 2026-07-26 — Loop closed: "what the money buys" is live on every district page

**What changed:** The TEA Snapshot join stopped being a markdown file and
became the product. New `#outcomes-section` on the district page, above the
peer insights, plus `GET /district/{id}/outcomes` and
`scripts/build_outcomes_data.py` → `static/outcomes_data.json`.

**The section, in order (deliberate):**
1. **Who the district teaches** comes first — % econ disadvantaged, emergent
   bilingual, special ed, each against the state. Districts serving more
   students in poverty score lower on average, so leading with this is what
   makes every comparison beneath it legitimate rather than misleading.
2. **Seven measures vs peers AND state**: teacher turnover, experience,
   STAAR, attendance, graduation, salary, students per teacher. Peers come
   from the same exogenous k-NN graph (`static/map_data.json`) the rest of
   the site uses, so "vs peers" means one thing everywhere.
3. **Scored against what its student population predicts**, with the model's
   42% R² inline and "treat it as a question, not a verdict" in bold.
4. **The statewide lever chart** — turnover 10.12% vs spending 0.01%.

Pittsburg ISD is the whole thesis on one screen: 77% economically
disadvantaged, pays teachers *less* than peers ($51k vs $55k), keeps them
anyway (13.9% turnover vs 24.8%), scores 18 points above prediction.

**Design decisions worth keeping:**
- Payload is **precomputed static**, not queried — none of it changes between
  annual TEA releases. Consequence: `/outcomes` works with **no database at
  all**, which `test_outcomes_served_without_a_database` asserts.
- Cached per warm instance and **sliced per request**. Shipping all 713 KB to
  a browser to render one district would be waste.
- Compact by construction: labels/units/state medians live once in `meta`
  instead of being repeated 1,205 times (1.7 MB → 713 KB). Per district a
  measure is just `[own value, peer median]`.

**Gotchas:**
- Rebuild `static/outcomes_data.json` after any new TEA release — it is a
  build artifact, and it IS committed (unlike `data/*.csv`) because the API
  serves it directly.
- `.vercelignore` must not exclude `static/` or the endpoint 503s in prod.
- Deploy verified the right way: rendered against **production** through
  `scratchpad/liveproxy.py`, desktop and phone, no page errors, no
  horizontal overflow.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted on
2026-07-25 — still outstanding, the Vercel one deploys to production.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, map keyboard/SR path,
PR #2 review. Product-wise the obvious next step is an outcomes lens on the
state map (colour by "beats expectation") and a turnover early-warning.

---

## 2026-07-25 — DEPLOYED. Two failures found: a broken build and a seat block

**What changed:** Everything from this session is live and verified in a real
browser against production. `dpl_5AtjJ2nPd6jqdjdQA9KBJ4uRYAUf` + favicon deploy.

**Why nothing had deployed all session — two independent causes:**

1. 🔴 **Every build was failing.** Vercel's FastAPI preset now builds with
   `uv`, which needs a PEP 621 `[project]` table. Ours had only
   `[tool.ruff]`/`[tool.pytest]`, so every build died on
   `Failed to run "uv lock": No 'project' table found in pyproject.toml`.
   Fixed by adding `[project]` with the RUNTIME deps only (mirrors
   requirements-vercel.txt — no pandas/matplotlib/plotly/openpyxl) plus
   `[tool.uv] package = false` (it's an app, not a library). **`uv lock`
   locally is the pre-flight check** before any deploy now.
2. 🔴 **Deploys came back `BLOCKED`, which is NOT a build failure.**
   `readyStateReason: Git author noreply@anthropic.com must have access to
   the team TAG-ai`, `seatBlock.blockCode = TEAM_ACCESS_REQUIRED`. Vercel
   **Pro bills per seat and refuses deployments whose git commit author has
   no seat.** Commits were authored `Claude <noreply@anthropic.com>`. Fixed
   by setting `git config user.email` to the repo owner; the
   `Co-Authored-By` trailer still records the AI author. **Keep it that way
   or deploys silently block again.**

Also added `.vercelignore` — the CLI was uploading `data/` (~19 MB of CSVs)
on every deploy, which is what made the first attempt time out at 10 minutes.
Upload is now 1.6 KB. And an inline data-URI favicon (every page load was
404ing on `/favicon.ico`).

**Verified live, not assumed:** `/health` healthy+connected; `/dollar/texas`
returns $109,448,637,486 across 1,202 districts and 5,528,915 students,
pennies summing to exactly 100; `/district/043905/dollar` 200. Rendered in
headless Chromium: hero reads "Texas school districts spend $109.4 billion a
year"; hovering a penny fills the guide panel; the pinned atom card reads
"Frisco ISD puts 3¢ more of every dollar into debt payments than similar
districts — $34,726,731 a year". **The map runs**: canvas 1724×1068 with ink,
search pins Frisco ISD, panel populates. Zero page errors.

**Gotchas:**
- Headless Chromium still cannot TLS through the agent proxy. To browser-test
  *production*, run `scratchpad/liveproxy.py` — it fetches live over HTTPS
  server-side and re-serves on `127.0.0.1:8799`, so Chromium renders exactly
  what production returns.
- Deployment state must be read from the API (`readyStateReason`, `seatBlock`),
  not inferred from the CLI. `BLOCKED` looks like a build failure and isn't.
- Credentials were staged to a 0600 file, used, then `shred -u`'d; `.vercel/`
  is gitignored and was removed. Working tree verified clean of tokens.

**Open items:** 🔴 **rotate the Vercel, Supabase and GitHub PATs pasted into
chat on 2026-07-25** (they are in the transcript; the Vercel one has deploy
rights). Then: surface the TEA Snapshot findings in the product, read-only DB
role for NLP, `/query` threadpool + timeout, real rate limiting, analytics,
Supabase idle-pause keep-alive, map keyboard/SR path, PR #2 review.

---

## 2026-07-25 — TEA Snapshot ingested: the project now has outcomes, students and teachers

**What changed:** `scripts/ingest_tea_snapshot.py` (self-downloading) and
`scripts/analyze_outcomes.py`, plus `docs/WHAT_A_DOLLAR_BUYS.md` and
`docs/findings_outcomes.json`. 19,441 district-years, 44 fields, 2009–2024.

**Where the data comes from:** TEA Snapshot "District and Charter Detail".
The download page is a form, not links — `POST` to
`https://rptsvr1.tea.texas.gov/perfreport/snapshot/push.cgi` with
`level=district`, `set=<2-digit year>`, `suf=.dat|.lyt`. Years 1995–2024 are
available. `.lyt` is the layout/definition file and you need it.

**Why this is the unlock:** PEIMS says where money GOES. Snapshot adds who
the students are (% econ disadvantaged, emergent bilingual, special ed),
the workforce (teacher salary, students per teacher, experience, **turnover**),
the tax base (taxable value per pupil, adopted tax rate, % revenue state/
federal), and outcomes (STAAR, graduation, attendance, accountability
rating). Joined on district_number + year.

**Headline findings** (associations, not causation — see the doc):
- Student need explains **33.4%** of the STAAR spread between districts;
  spending per student adds **0.0%** on top of it.
- Same control applied to every lever: **teacher turnover explains 10.12%**
  of what need leaves unexplained, vs **0.01%** for spending per student.
  Teacher experience and % new teachers rank 2nd and 3rd. Every money
  variable is near the bottom.
- Richest fifth of districts by property value spend **15% more** per
  student than the poorest fifth while serving 19 points less economic
  disadvantage; the poorest fifth carries **28% teacher turnover**.

**Gotchas:**
- **Map fields by layout DESCRIPTION, never by column name.** TEA embeds the
  reporting year in every variable (`DDA00A001S24R` vs `DDA00A001S18R`) and
  renames measures. Name-based mapping silently returns nothing.
- Older years call the key `COUNTY-DISTRICT NUMBER`, not `DISTRICT NUMBER`;
  ELL is `ENGLISH LANGUAGE LEARNERS` pre-2018 and `ENGLISH LEARNERS` after.
  The first pass silently produced **0 rows for 2009–2012** because of this.
- **Testing standard breaks at 2018** (phase-in satisfactory → "Approaches").
  The ingest stamps `test_standard` per row. No trend line may cross it.
- No accountability ratings in 2023/24 (litigation); no STAAR before 2013;
  2020–21 are pandemic years.
- FERPA-masked cells (`.`, `-1`, `*`) are **missing, not zero**.
- Join validates at 94.1%, and TEA's own operating-spend-per-pupil agrees
  with ours to a median 2.9% (different enrollment denominators — don't mix
  the two sources inside one calculation).
- `data/*.csv` is gitignored, so the ingest downloads its own inputs.

**Open items:** surface this in the product — none of it is in the API or UI
yet. Everything from the previous entry still applies, deploy included.

---

## 2026-07-25 — Guided dollar (macro→micro→atom) + landing page rebuilt from a browser audit

**What changed:** **Committed and pushed but NOT DEPLOYED** — see Gotchas.

(0) 🔴 **`static/map.html` has been completely broken in production since
2026-07-24.** It declared `const a` twice in the same function scope — a
hard SyntaxError, so the whole script never parsed: no canvas, no panel,
no search. Introduced in `04a4385` and shipped, because that deploy was
"verified" by grepping the served HTML for strings, which proves bytes
arrived and nothing more. **Never verify a JS change by grepping HTML.**
Fixed and confirmed in a real browser (canvas sizes and draws, search
pins, panel and readout populate, no page errors). Its `.catch()` also
wrote to a `.support` element that does not exist on that page, so any
data failure threw inside the catch and hid the cause — now reports into
`#readout`. Emoji removed from both pages; district names title-cased on
the map too.

(a) *Guided dollar.* New `GET /district/{id}/dollar` is now the single
definition of the 100-penny dollar for every client: largest-remainder
shares (always exactly 100), peer + statewide median shares rescaled to a
whole dollar, and dollars-at-stake from median dollars *per student* so
they stay real money. `static/index.html` renders it as: hover/tap/focus
any penny → a guide panel giving contents in plain English, TEA codes,
peer + state comparison and the annual dollar difference; click → an atom
card with a 17-year share sparkline against the peer line, sub-components,
and the question a board member or reporter should ask; a TEXAS ›
DISTRICT › CATEGORY zoom ladder; three stacked 100¢ bars (you / peers /
all Texas). Two categories the old client-side split buried in the
residual — safety & technology, community services — are now named.

(b) *Landing page.* Audited live in headless Chromium and rebuilt: the
7-step tour no longer auto-opens over the page; real hero with the
statewide total in the headline; the hero *shows* the live statewide
dollar (new `GET /dollar/texas`, pooled — no rescaling needed); quick-pick
chips from `/stats.largest_districts` plus type-ahead; hero collapses once
a district is picked; serif display face against the sans body; district
names title-cased on entry to state; header count now read from `/stats`.

**Why:** User asked for hover guidance and a macro→micro→atom path that
answers the questions only this data can answer, then asked for a browser
audit of the landing page. The audit found the first impression was a grey
modal over a search box — no headline, no number, no picture — in an 892px
column on a 1440px screen, with 1,202 vs 1,310 districts contradicting
each other between header and stats.

**Gotchas:**
- 🔴 **Deploys are not automatic from this branch.** Pushing produced no
  new deployment (polled 4 min; `/district/{id}/dollar` still 404s live).
  Earlier deploys this session used the user's Vercel PAT, since shredded;
  the Vercel MCP tools need interactive approval. Everything above is on
  the branch and unverified in production.
- Headless Chromium cannot TLS through the agent proxy (`ERR_CONNECTION_RESET`,
  no relay failure logged). Workaround that worked: a local plain-HTTP
  harness on 127.0.0.1 serving the working-tree HTML and proxying the API
  server-side, with `/dollar` computed by importing the real functions from
  `src.api` — which validated the endpoint math on live data before deploy.
  Chromium path is `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
- **A page can serve 200 and still be entirely dead.** Extract the
  `<script>` block and `node --check` it in CI, and render the page in
  headless Chromium against the local harness before claiming a UI works.
  Both pages now parse clean; add this to the verify step in CLAUDE.md.
- Penny grid: dimming at .18 opacity destroyed the grid's shape, and
  `transform:scale()` on the highlighted squares made neighbours collide.
  Use ~.3 opacity and an outline instead.
- skills.sh pages for the five requested skills are discovery stubs, not
  skill text; only `anthropics/skills/frontend-design` returned usable
  principles. Installing them needs an interactive session.

**Open items:** unchanged, plus: get this deployed and re-verify live;
map keyboard/screen-reader path. Still open: credential rotation
(user-side, 🔴), read-only DB role for NLP, `/query` threadpool + timeout,
real rate limiting, analytics, Supabase idle-pause keep-alive, PR #2
awaiting review — do not merge.

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
  `OPENAI_API_KEY`. Live: https://txisd.dev
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

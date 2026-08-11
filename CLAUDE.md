# Texas ISD Finances — Agent Boot File

You have no memory of previous sessions. This file plus
`docs/ENGINEERING_LOG.md` IS your memory. **Run `/ariba` to catch up before
substantial work, and `/ariba save` before ending any session that changed
anything.** (Skill: `.claude/skills/ariba/SKILL.md`.)

## What this project is

Public transparency portal for Texas school district finances (TEA PEIMS
data, fiscal 2009–2025). FastAPI serves a static portal + JSON API;
LangChain 1.x + OpenAI turns plain-English questions into SQL against two
read-only Postgres views on Supabase. MIT-licensed, built for public use.

## Production (live)

| Thing | Value |
|---|---|
| ⚠️ vercel.json | **Must have NO `rewrites` block.** Vercel changed backend-framework routing so an internal rewrite now passes the DESTINATION path to the app — the old `/(.*) → /api/index` rewrite made FastAPI receive `/api/index` for every request and 404 the entire site while the build still reported READY. The `fastapi` framework preset routes to `api/index.py` on its own. |
| Vercel team | **TAG-ai** (`tag-ai-projects`) — NOT GOAT-UIX. Two teams each hold a project named `texas-isd-finances`; only the TAG-ai one owns `txisd.dev`. Always `--scope tag-ai-projects`. `vercel link` rewrites `vercel.json` and the project framework — `cat vercel.json` after. |
| Live portal | **https://txisd.dev** — the custom domain, use it everywhere. `texas-isd-finances.vercel.app` also resolves but is the prototype URL and must not appear in pages, docs or citations (a test enforces this). Vercel project `texas-isd-finances`, account `tag-ai`. |
| API docs | https://txisd.dev/docs |
| Health check | `GET /health` → expect `{"status":"healthy","database":"connected"}` |
| Database | Supabase project `texas-isd-finances`, ref `zwhvabkvrexphlskubog`, us-east-1, org "GOAT-UIX" |
| Data loaded | 20,587 rows · 1,310 districts · fiscal 2009–2025 (TEA "Summarized PEIMS Actual Financial Data") |
| Secrets | ONLY in Vercel env vars (`SUPABASE_DB_URL`, `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`, `CRON_SECRET`, `SITE_PASSWORD`). Never in repo, never in this file, never in the log. |
| LLM provider | One config: `src/llm_config.py`. `DEEPSEEK_API_KEY` present → DeepSeek (`deepseek-v4-flash` @ `https://api.deepseek.com`); else OpenAI. DeepSeek is OpenAI-protocol compatible (incl. tool calls), so `ChatOpenAI` serves both — only base URL + model change. `/health` reports the live provider. |
| Site lock | `SITE_PASSWORD` set → whole site behind a browser password. `/health` and `/api/cron/*` stay open by design. Unset it to go public. |
| GitHub | https://github.com/GusAI40/texas-isd-finances — default branch `master` (PR #1 merged 2026-07-23); work branch `claude/audit-public-launch-ocd7ra` restarts from master |

## Invariants (violate these and production breaks)

- **DB connections from deploys must use the Supabase pooler**, not the
  direct host (direct is IPv6-only). Serverless (Vercel) uses transaction
  mode, port **6543**; the API sets asyncpg `statement_cache_size=0` to
  survive it — do not remove that.
- **LangChain is pinned `>=1.0,<2.0`**; the agent API is
  `langchain.agents.create_agent`. Legacy `create_sql_agent` does not exist
  anymore. `langchain-community` (SQL toolkit source) is sunset but
  functional — watch its issue #674 for the migration path.
- **`data/district_crosswalk.csv` is the district registry** (1,310 rows, committed, whitelisted in `.gitignore`). One row per district: TEA number, county + code, `brb_id`, charter flag, boundary flag, first/last year, **former names** (103) and **aliases** (37 — `Edgewood ISDa`, `Calhoun Co ISD`, `Aransas County ISD`). Built by `scripts/build_district_crosswalk.py`, and **load-bearing**: `Resolver.from_crosswalk()` registers current name + former names + aliases, so every name a district has ever carried resolves. Building the resolver from the finance file alone learned only the EARLIEST name — **64 of the 103 renamed districts could not be resolved by the name they go by today** ("Aransas County ISD" worked, "Rockport-Fulton ISD" did not), so any source using a current name was silently dropped. Now 0. It also turned the bond layer's 13 heuristic `prefix+county` matches into exact ones. Setup order: build the bond file first, then the crosswalk (the builder falls back to `from_tea` if the crosswalk is absent). **A UUID was considered and rejected**: the TEA number already survives renames (103 did, none was ever reused), it is the only id a reader can check against the state, and its first three digits ARE the county code — which is what fixed the bond join. A minted id would add a third thing to sync, would not touch the hard step (sources send NAMES), and is verifiable against nobody but us. `tests/test_crosswalk.py` fails the build if any column looks minted.
- **`district_number` is a 6-digit string** (e.g. `057905` = Dallas ISD).
  Any pandas read of the CSV needs `dtype={"district_number": str}` or
  leading zeros die.
- **Setup order is import-first**: `scripts/prepare_data.py` →
  `scripts/import_to_supabase.py` (creates the 140-col table) → run
  `sql/create_tables.sql` (adds PK/indexes/views/matview/RLS/grants).
- **Vercel builds with `uv` from the `[project]` table in `pyproject.toml`**
  (runtime deps only; no pandas/matplotlib — bundle cap 500 MB).
  `requirements-vercel.txt` mirrors it. Pre-flight any deploy with
  `uv lock --dry-run`; a missing `[project]` table fails every build.
- **Commits must be authored by a Vercel team seat holder.** Vercel Pro
  bills per seat and returns `BLOCKED` /`TEAM_ACCESS_REQUIRED` for deploys
  whose git author has no seat — it looks like a build failure and isn't.
  Keep `git config user.email` on the repo owner; `Co-Authored-By` records
  the AI author.
- **After any data import**: `REFRESH MATERIALIZED VIEW v_anomaly_flags;`
- **The NLP prompt must keep the "counting is not limiting" rule.** It once
  said "default LIMIT 100", so the agent LIMITed a `SELECT DISTINCT` and
  answered "100 districts" instead of 1,310 — intermittently. Never let a
  default LIMIT be described without excluding aggregates.
- **`/districts?limit=N` returns the first N ALPHABETICALLY**, not a sample.
  Never resolve a district by scanning it; use the district's own endpoints.
- **`static/district_geo.json` is a committed build artifact too.** Rebuild
  order after a TEA release: `build_outcomes_data.py` → `build_district_geo.py`
  (the latter merges the former's measures in).
- **`static/outcomes_data.json` is a committed build artifact** — the API
  serves it directly and it works with no database. Rebuild it after any new
  TEA release: `scripts/ingest_tea_snapshot.py --download` then
  `scripts/build_outcomes_data.py`. `.vercelignore` must never exclude
  `static/`.
- Local sandbox note: direct Postgres (port 5432/6543) may be blocked in
  the remote dev container — use the Supabase Management API
  (`POST /v1/projects/{ref}/database/query`) for SQL and PostgREST for bulk
  data, both over HTTPS.

## Verify before claiming anything works

```bash
ruff check . && python -m pytest -q       # all must pass (count drifts; don't hardcode it)
curl -s https://txisd.dev/health
python scripts/verify_live.py             # does PRODUCTION serve what this tree says?
```

**`verify_live.py` is the check the other three could not make.**
`verify_sources.py` proves the publisher's file is the publisher's file,
`test_provenance.py` re-derives every headline from it, `verify_artifacts.py`
rebuilds and byte-diffs — and a repo can pass all three while the deployed site
serves something else entirely. That is not hypothetical: the bond layer ran
live for weeks two years stale, publicly naming districts as having no
voter-approved bond after they had passed one, with a green suite throughout.
It exits non-zero on drift, so it works as a deploy gate or a cron. Run it
against a local server (`--base http://127.0.0.1:8000`) to confirm a build
before shipping it.

**Static pages need their own check — a 200 response proves nothing.** A
`const` redeclaration once killed `static/map.html` entirely while the page
still served 200 and grepped fine. Always parse the script, and render it:

```bash
python3 -c "import re;s=open('static/map.html').read();\
open('/tmp/m.js','w').write(re.findall(r'<script>(.*?)</script>',s,re.S)[-1])"
node --check /tmp/m.js                    # repeat for static/index.html
```

Never verify a UI change by grepping the served HTML for strings.

**Anything above the fold that depends on `localStorage` must be applied
before first paint** — inline `<script>` in `<head>` setting a class on
`documentElement`, plus CSS. Doing it in `boot()` causes a visible flash that
lasts as long as whatever `boot()` awaits first (this shipped once).

To render *production* in a browser (Chromium can't TLS through the agent
proxy), run `scratchpad/liveproxy.py` and point Playwright at
`127.0.0.1:8799`.

## Current Status (updated 2026-08-11 — keep this a snapshot, history goes in the log)

- ✅ Live in production, all endpoints verified including end-to-end NLP.
- ✅ Public portal is now the **Texas ISD Financial Resource Guide**: white-minimalist McKinsey/SWD design, penny-of-the-dollar visual, 6 audience lenses, share cards, Methods & citation section, AI disclosure + TAG footer.
- ✅ `static/map.html` ("seating chart" of all 1,202 districts) works on phones — pan/pinch/tap; landmarks + named neighborhoods + plain axes.
- ✅ **"What the money buys" live on every district page** — student need, teacher turnover/experience/salary, STAAR, attendance, graduation, each vs structural peers + state; scored against what demographics predict; statewide lever chart (turnover 10.12% vs spending 0.01% — **cross-sectional, now labelled as description not leverage**; the within-district effects are ~25x smaller, see `scripts/build_economics_data.py`). Data: TEA Snapshot 2009–2024 joined to PEIMS (`scripts/ingest_tea_snapshot.py`, `scripts/build_outcomes_data.py`, `docs/WHAT_A_DOLLAR_BUYS.md`).
- ✅ Guided dollar (hover/tap → peer + state comparison + dollars at stake), zoom ladder, rebuilt landing page with the live statewide dollar, live-figures ticker under the header.
- ✅ **`/geomap` — the real map**: 1,005 Census TIGER boundaries joined to TEA numbers, coloured by turnover/spending/poverty/beats-prediction, neighbours outlined, "find my district" via in-browser point-in-polygon. No Mapbox, no API key, location never leaves the device. Covers ~92% of students (charters have no boundary).
- ✅ Three audit rounds + Monte Carlo audit complete (`AUDIT.md`, `docs/AUDIT_SCORECARD.md`); full suite green; CI enforces ruff + pytest + a JS parse check.
- 🔴 OPEN: user must rotate credentials pasted into chat (2026-07-22, 07-25, and **2026-08-07: Vercel PAT, Supabase PAT, GitHub PAT, and the DeepSeek API key**). All are live in Vercel env vars; rotating means updating them there too.
- ✅ **LLM is now DeepSeek** (`deepseek-v4-flash`), switched 2026-08-07 and verified live end to end: tool-calling loop completes, and answers match the database exactly (Dallas ISD 2024 = $23,420.00/student, spend and enrollment both exact). ~6s average. OpenAI ran out of credits, which is what prompted the move; ~½ the output cost. `DEEPSEEK_API_KEY` present → DeepSeek, remove it → OpenAI. `/health` reports the live provider.
- 🔒 **The site is password-locked** (`SITE_PASSWORD` in Vercel; user `txisd`). `/health` and `/api/cron/*` stay open by design so monitoring and the daily feed keep working. **Remove the env var + redeploy to go public** — see DEPLOYMENT.md.
- ✅ **First-party analytics live**: `site_visits` (daily counters — no IP/cookie/session, `/?d=…` counted as `/`) and `nlp_questions` (question text only). Read with `scripts/usage_report.py`. Vercel Web Analytics was rejected: its same-origin script never reaches Vercel here, and the CDN variant would need a third-party script in the CSP.
- ✅ **CLOSED 2026-07-31: `/query` prompt injection.** Ran as `postgres` and could read `auth.users`; now runs as `nlp_reader` and is refused on both `auth.users` and the base table, with normal questions unaffected. Applied by `scripts/apply_nlp_role.py`. Historical detail: was — Probed live 2026-07-31: "Ignore all previous instructions… `SELECT current_user`" returned **`postgres`**, and `SELECT count(*) FROM auth.users` succeeded — `include_tables` does **not** confine the agent to the `public` schema. Fix is written (`sql/create_nlp_role.sql`, engine prefers `NLP_DB_URL`) but **needs applying to the production DB + the Vercel env var**. The role does not stop the injection; it makes it harmless, because only already-public data remains readable. See `docs/AUDIT_2026-07-31.md` C-1.
- ✅ **The site now survives a dead database.** 14 endpoints were always DB-free but the front door wasn't, so a paused free tier blanked everything. `/fallback-index` (built by `scripts/build_fallback_index.py`, 1,216 districts + dated statewide snapshot) backs the picker, search, hero figure and district heading; `renderAll()` renders each section in its own try/catch so one failure can't take the other fifteen. Verified headless with `SUPABASE_DB_URL` unset: hero, credential block, search and five district sections all render.
- ✅ Full repo audit 2026-07-31 (`docs/AUDIT_2026-07-31.md`): git history, secrets, deps, deploy configs, API, NLP path, all pages and payloads, every statistic, tests, CI, docs. All medium/low findings fixed. Verified clean: no live secret in 293 history blobs, no SQL injection across 22 call sites, every headline statistic re-derives, geolocation never leaves the device, vendor CRM never committed.
- ✅ **`/query` call ceiling now counts in the DB** (`sql/create_nlp_usage.sql`, atomic conditional-increment), so `QUERY_GLOBAL_LIMIT`/min and `QUERY_DAILY_LIMIT`/day hold across every serverless instance instead of per-process. Fails open if the table is missing (logs a warning, falls back to per-instance). **Apply the SQL to production to activate it.** Still set a monthly OpenAI usage cap — these bound calls, not dollars.
- ✅ Payload sizes measured and dismissed: Vercel serves Brotli, so `/district-geo` is 220 KB on the wire and every per-district payload is 1–2 KB. PR #2 awaiting user review (do not merge).
- ✅ **HISD takeover analysis** — `/takeover/houston` from `static/takeover_data.json`. Difference-in-differences vs 13 districts matched on PRE-takeover size+poverty. Houston **+5.5 vs +0.0**, rank 1 of 14, 1st of 30 large districts. Parallel pre-trends hold. **Special education students went backwards (−1.8 vs comparison)** — reported, not buried. `scripts/build_takeover_data.py`.
- ✅ **Equity layer** — `/district/{id}/equity` + `/equity/texas` from `static/equity_data.json` (TEA District STAAR, SY 2024 + 2025, 99.8% join). Headlines **how a district's low-income students do**, benchmarked against poor students statewide — **never the gap**, which correlates ~0 with how poor students actually do. Reported at **Meets**, not Approaches.
- ✅ **Bond story** — `/district/{id}/bonds` + `/bonds/texas` from `static/bond_data.json`. **Source corrected 2026-08-11**: this ran for weeks on a municipal-advisory vendor's Excel export credited to the *Texas Secretary of State*, with a note claiming no agency publishes school bond elections statewide. Both false — the **Texas Bond Review Board** publishes all of them on `data.texas.gov/d/kbmc-qmvg` and always did. Now ingested first-party by `scripts/ingest_bond_elections.py`: **4,992 decided propositions 1958–2026, 952 districts, 100% matched**, $327.6B asked. The vendor file was two years stale (404 propositions short, all recent) and carried spreadsheet `Subtotal:`/`Grand Total:` rows. Two published claims were corrected — **Wills Point ISD** (listed as never having a voter-approved bond; it carried $69.9M on 2025-11-04 after five straight defeats over 21 years) and **Louise ISD** ($9M, 2026-05-02). `scripts/district_match.py` resolves by name+county; `scripts/audit_bond_match.py` fails the build if a shared name resolves without the county agreeing. Carries the **bond→outcome test**: passed −0.27 vs defeated −1.58, **+1.31, CI +0.07/+2.55, p=0.038** (310 bonds, 153 districts) — **unchanged by the refresh**, because the new elections are too recent to have outcomes. Ships with a `fragile` flag; the page says *suggestive, not settled*. **Never ingest the two vendor companion CSVs — they carry a CRM (named reps, revenue, commissions). Going first-party removed the temptation.**
- ✅ **Debt outstanding — the stock, not the flow** (NEW 2026-08-11) — `/debt/texas` + `/district/{id}/debt` + the "What is still owed" section on `/forensics`, from `static/debt_data.json` (no DB). Every previous debt figure was PEIMS debt *service* — what was paid in a year. This is the balance: **Texas districts owe $236.7B as of fiscal 2025 — $148.4B principal and $88.3B of interest nobody has paid yet (37.3%)** — and on debt already sold it **clears in 2061**. **169 districts still carry capital appreciation bonds**, which pay nothing until maturity: **$2.36B of deferred interest against $440M of principal**. First-party from the Board's own issuer index and per-issuer series (`scripts/ingest_brb_debt.py` → `scripts/build_debt_data.py`), never the aggregator that led us to it. 967 issuers, 100% resolved to TEA numbers.
  ⚠️ **The repayment ratio is only ever taken at a district's PEAK year.** On an outstanding balance it climbs by itself as principal retires: Leander ISD reads 4.5x in 2014, 20.1x in 2025 and 396x in 2030 with no deal having changed. Also refused where the series has a **gap** (Ysleta ISD reports 2005–2012 then 2020+; its largest reported total postdates the 2015 4:1 cap, so no such deal could exist) or **predates the record** (La Joya opens at 90.5x). 63 districts get a ratio (1.22x–10.84x); 106 keep their deferred interest without one. `tests/test_debt.py` enforces all three refusals.
  ⚠️ **Dedupe by the Board's id, never by name.** Its index lists three issuers under two names each — including one id serving identical data as both "Highland Park ISD (Dallas)" and "Highland Park ISD [Amarillo]". Matching on name double-counts $406.5M.
  ⚠️ Rows after fiscal 2025 are the **amortisation schedule** for debt already sold — not history, not a forecast. Never sum them with history.
- ✅ **Economics layer** (incl. **who pays**: local/state/federal from GROSS local collections — TEA reports M&O revenue net of recapture, so net understates property-funded districts; statewide 54/37/9) — `/district/{id}/economics` + `/economics/texas`, served from `static/economics_data.json` (no DB). What you pay (tax bill on a $300k home, what leaves under recapture), where it goes (teaching vs buildings vs debt — **debt sits OUTSIDE TEA's operating total, compose don't subtract**), what each lever actually bought (within-district first differences, 3-yr, clustered SEs), and who does better (matched persistent outperformers). `scripts/ingest_tea_property.py` + `scripts/build_economics_data.py`.
- ✅ **Forensic file** — `/forensics` page + `/forensics/texas` + `/district/{id}/forensics`, served from `static/forensic_data.json` (no DB). Composes four questions Texas publishes in four incompatible files: what sits **outside** TEA's operating total ($13.9B/yr in debt service statewide, median $1,538/student), **who pays** from GROSS local collections, what the **ballot** promised, and where results **landed** vs what need predicts. **Deliberately no combined score** and no per-district causal claim; every flag states a published number against a published threshold, and tests enforce both. `scripts/build_forensic_data.py`.
- ✅ **17-year trajectory** — `/trends/texas` + `/district/{id}/trends` + the "Seventeen years" section on `/forensics`, from `static/trend_data.json` (no DB). Turns the snapshot into a direction: six measures per district, fiscal 2009–2025, in constant 2024 dollars, each against the state's own line. The squeeze, statewide: **instruction's share of the operating dollar 57.8% → 54.5%** (−$369/student real) while **debt service $1,507 → $2,441** and **security $96 → $232 (2.4x)**; federal peaked $2,798 (2022) → $1,432; and in **2025 operating revenue fell below operating spending statewide for the first time in the window (+$3.0B 2022 → −$1.6B)**, with 44.4% of districts short, enrolling 67.7% of students. Every headline is re-derived on a **balanced panel** of the 1,142 districts reporting in both end years (−3.2 vs −3.3 pts), and tests assert each finding still matches its own series. `scripts/build_trend_data.py`.
  ⚠️ **Operating balance is operating revenue vs operating spending ONLY.** `all_funds_other_revenue` tracks debt service almost exactly year by year — it IS the I&S debt levy — so including it while excluding debt service understates deficits badly (it gives 12% for 2025 instead of 44%). Never use the `..._and_other_revenue_and_reca` column for an operating comparison.
- ✅ **Provenance chain closed** — `tests/test_provenance.py` (23 tests) re-derives EVERY published headline from the state's own file, longhand, without importing any builder: a wrong number can no longer validate itself. The 18 MB CSV is not committed, so `scripts/build_provenance_fixture.py` freezes the per-year statewide sums (26 KB, `tests/fixtures/provenance.json`) plus a **SHA-256 of the source**, and 17 of the 23 run with no CSV present — the guarantee holds in CI. `scripts/verify_artifacts.py` closes the last link by rebuilding every artefact and diffing byte for byte, which is the only check that catches a builder edited and never re-run, or an upstream restatement. Chain: TEA file → CSV (hashed) → fixture (committed) → artefact (diffed) → page (tested).
- ✅ **`verify_sources.py` now checks ATTRIBUTION, not just liveness** (2026-08-11). It passed the wrong bond publisher every run, because the Secretary of State page returns 200 from a `sos.state.tx.us` host — it proved the link was *alive* and that the host matched the publisher we had *wrongly named*. Every source now declares `proves_it`: strings that must appear in what the URL actually serves. TEA's pages name their own product; the Census zip names its members in the archive header; `data.texas.gov` and `data.brb.texas.gov` declare an `attribution_url` pointing at their metadata/index API, which returns the publisher *as the State of Texas states it* — a stronger proof than our own claim. The old citation now fails the check. **A live link to the wrong file is worse than a dead one, because it looks checked.**
- ✅ **The reclassification caveat is RETIRED, with evidence** (`meta.reclassification_check`). Instruction's 57.8%→54.5% fall is real reallocation, not a recoding, four ways: the 16 function codes still sum to the reported operating total every year (0.9996–1.0000); risers +4.25 and fallers −4.25 cancel to a **zero residual**; **no single function absorbs it** (largest riser +1.07 vs instruction −3.26 — a recoding shows one bucket swallowing it); and it **predates COVID** (−1.75 by 2019) and **outlives the federal cliff** (−1.31 since 2022). Recomputed on every build so a future TEA release cannot quietly change the answer.
- ✅ **Window robustness published** (`meta.window_checks`): the finding holds on 17, 10 and 6-year windows (−3.27 / −2.32 / −2.43 pts; balanced panel 87.2% / 94.9% / 97.4%). A shorter window buys panel coverage and costs finding strength and makes nothing more accurate — so all three ship. **Agreement is the robustness result; disagreement would be the finding.**
- ✅ **MCP server** — `POST /mcp` speaks **Model Context Protocol 2026-07-28** (`src/mcp_protocol.py` wire format + `src/mcp_tools.py` tools, `docs/MCP.md`). Eight read-only tools over committed JSON: `find_district`, `district_money`, `district_forensics`, `district_trends`, `district_bonds`, `district_debt`, `texas_overview`, `compare_districts`. **Every result carries the payload's `limits`**, so caveats travel into someone else's chat attached to the number. **MRTR (SEP-2322) is wired to the name-collision problem**: a tool given an ambiguous district name returns `resultType: "input_required"` listing the real candidates with enrolment instead of guessing — thirteen Texas names belong to two districts each, and guessing is how bond history reached the wrong district once already. No `requestState` is minted (arguments are re-sent), so it stays stateless. **The connect-time `instructions` now read their figures from the artefact** — they claimed "4,588 bond elections" for as long as the bond layer was stale, and kept claiming it after the refresh. Hand-written, no SDK dependency — a bad dep fails every Vercel build, and the needed surface is three methods. **`/query` is deliberately NOT exposed** (prompt-injection history, spends DeepSeek tokens); every tool is a deterministic read with no DB, so it survives a paused Supabase. 2026-07-28 is what made this possible at all: it removed the `initialize` handshake and `Mcp-Session-Id`, so a stateless serverless app behind a round-robin no longer needs session affinity.
- ✅ **All of the above is LIVE** (deployed 2026-07-26): security headers, `/query` threadpool+timeout+global cap, table twins, property/tax/recapture ingest, economics layer.
- 🔴 OPEN: a fifth credential was pasted into chat 2026-08-11 (`od_live_…`, tryopendata.ai). Rotate with the other four. It was used read-only for discovery and never committed.
- ⏭️ NEXT: deploy this branch (not yet deployed — production still serves the vendor bond file and has no `/debt/*`); apply `sql/create_nlp_usage.sql` to production; write the HISD finding up for a reporter; then the **TAPR campus file** (teacher certification, and the 77% invisible above campus level). Older plan: bake outcomes in as the **spine** (every money fact ends in what it bought, with an error bar) — first the bond→outcome test on the district page; then the **HISD board-of-managers analysis** (did the 2023 takeover change results vs matched districts?); then the **TAPR campus file** for teacher certification.
- 📌 Measured within-district **at the Meets bar**: teacher pay +$5,000 → **+0.86** (CI +0.48/+1.23, the largest identifiable lever); class size −2 → +0.37; turnover −10 → +0.30 (**CI crosses zero**); spending +$2,000 → +0.15 (**crosses zero**); a passed building bond → −0.57 (crosses zero). The large thing is a persistent district effect, **77% unexplained**.
- ✅ **Silent failure is now visible** (2026-08-11) — `sql/create_cron_runs.sql` + `/api/cron/runs`. A job that never fires and a job that fires and writes nothing look identical from outside, which is how the intel cron failed silently for four days. Every firing records status (`ok`/`skipped`/`error`), duration and `rows_written`; `gap_days` and `wrote_nothing` are what you read. **The failure path had no record at all before this** — an exception 500'd and left nothing. Fails open if the table is missing. **Apply the SQL to production to activate it.**
- ✅ **One formatter, not three** (2026-08-11) — `src/format.py`. `_usd` existed in both `src/mcp_tools.py` (exact) and `scripts/isd_intel.py` (abbreviated) — **same name, opposite precision**: the briefing rendered $1.5M as **"$2M"** and $1,234 as "$1K", and still carried the `$-354` sign bug fixed in mcp_tools months earlier. Three name formatters (`_title`, `nice_name`, `_district_name`) each independently produced `D'hanis ISD` and `S And S CISD`. `tests/test_format.py` locks every one of those defects.
- 🟡 WATCH: Supabase free tier pauses after ~7 days idle → portal shows "database not connected" until woken in dashboard. Vercel Hobby is non-commercial; upgrade both if pursuing revenue.

## Key docs

`AUDIT.md` (all findings) · `DEPLOYMENT.md` (launch runbook) ·
`PROJECT_MAP.md` (visual map) · `docs/ENGINEERING_LOG.md` (session memory).

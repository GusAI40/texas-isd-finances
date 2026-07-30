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
| Secrets | ONLY in Vercel env vars (`SUPABASE_DB_URL`, `OPENAI_API_KEY`). Never in repo, never in this file, never in the log. |
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
ruff check . && python -m pytest -q       # 54 tests, all must pass
curl -s https://txisd.dev/health
```

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

## Current Status (updated 2026-07-30 — keep this a snapshot, history goes in the log)

- ✅ Live in production, all endpoints verified including end-to-end NLP.
- ✅ Public portal is now the **Texas ISD Financial Resource Guide**: white-minimalist McKinsey/SWD design, penny-of-the-dollar visual, 6 audience lenses, share cards, Methods & citation section, AI disclosure + TAG footer.
- ✅ `static/map.html` ("seating chart" of all 1,202 districts) works on phones — pan/pinch/tap; landmarks + named neighborhoods + plain axes.
- ✅ **"What the money buys" live on every district page** — student need, teacher turnover/experience/salary, STAAR, attendance, graduation, each vs structural peers + state; scored against what demographics predict; statewide lever chart (turnover 10.12% vs spending 0.01% — **cross-sectional, now labelled as description not leverage**; the within-district effects are ~25x smaller, see `scripts/build_economics_data.py`). Data: TEA Snapshot 2009–2024 joined to PEIMS (`scripts/ingest_tea_snapshot.py`, `scripts/build_outcomes_data.py`, `docs/WHAT_A_DOLLAR_BUYS.md`).
- ✅ Guided dollar (hover/tap → peer + state comparison + dollars at stake), zoom ladder, rebuilt landing page with the live statewide dollar, live-figures ticker under the header.
- ✅ **`/geomap` — the real map**: 1,005 Census TIGER boundaries joined to TEA numbers, coloured by turnover/spending/poverty/beats-prediction, neighbours outlined, "find my district" via in-browser point-in-polygon. No Mapbox, no API key, location never leaves the device. Covers ~92% of students (charters have no boundary).
- ✅ Three audit rounds + Monte Carlo audit complete (`AUDIT.md`, `docs/AUDIT_SCORECARD.md`); 54 tests green; CI enforces ruff+pytest.
- 🔴 OPEN: user must rotate credentials pasted into chat on 2026-07-22 and 2026-07-25 (OpenAI/GitHub/Hetzner/Anthropic etc.); OpenAI key in Vercel env needs updating after rotation.
- ✅ Hardening complete in code. Read-only DB role shipped as `sql/create_nlp_role.sql` (`nlp_reader`; engine prefers `NLP_DB_URL`, falls back to the owner URL) — **still needs applying to the production DB + the Vercel env var; until then `/query` runs model-written SQL as owner.** Payload sizes measured and dismissed: Vercel serves Brotli, so `/district-geo` is 220 KB on the wire and every per-district payload is 1–2 KB. PR #2 awaiting user review (do not merge).
- ✅ **HISD takeover analysis** — `/takeover/houston` from `static/takeover_data.json`. Difference-in-differences vs 13 districts matched on PRE-takeover size+poverty. Houston **+5.5 vs +0.0**, rank 1 of 14, 1st of 30 large districts. Parallel pre-trends hold. **Special education students went backwards (−1.8 vs comparison)** — reported, not buried. `scripts/build_takeover_data.py`.
- ✅ **Equity layer** — `/district/{id}/equity` + `/equity/texas` from `static/equity_data.json` (TEA District STAAR, SY 2024 + 2025, 99.8% join). Headlines **how a district's low-income students do**, benchmarked against poor students statewide — **never the gap**, which correlates ~0 with how poor students actually do. Reported at **Meets**, not Approaches.
- ✅ **Bond story** — `/district/{id}/bonds` + `/bonds/texas` from `static/bond_data.json`. 4,588 decided propositions 1958–2024, 911 districts, 96.8% name-matched. **The ballot is the only public record of what school debt was FOR** — TEA does not itemise facilities. Four-beat narrative on the district page. `scripts/build_bond_data.py`. Carries the **bond→outcome test**: passed −0.38 vs defeated −1.58, difference +1.20, **p=0.061, not distinguishable from zero** (304 bonds, 151 districts). **Never ingest the two companion CSVs — they carry a vendor's CRM (named reps, revenue, commissions).**
- ✅ **Economics layer** (incl. **who pays**: local/state/federal from GROSS local collections — TEA reports M&O revenue net of recapture, so net understates property-funded districts; statewide 54/37/9) — `/district/{id}/economics` + `/economics/texas`, served from `static/economics_data.json` (no DB). What you pay (tax bill on a $300k home, what leaves under recapture), where it goes (teaching vs buildings vs debt — **debt sits OUTSIDE TEA's operating total, compose don't subtract**), what each lever actually bought (within-district first differences, 3-yr, clustered SEs), and who does better (matched persistent outperformers). `scripts/ingest_tea_property.py` + `scripts/build_economics_data.py`.
- ✅ **All of the above is LIVE** (deployed 2026-07-26): security headers, `/query` threadpool+timeout+global cap, table twins, property/tax/recapture ingest, economics layer.
- ⏭️ NEXT: write the HISD finding up for a reporter; then the **TAPR campus file** (teacher certification, and the 77% invisible above campus level). Older plan: bake outcomes in as the **spine** (every money fact ends in what it bought, with an error bar) — first the bond→outcome test on the district page; then the **HISD board-of-managers analysis** (did the 2023 takeover change results vs matched districts?); then the **TAPR campus file** for teacher certification.
- 📌 Measured within-district **at the Meets bar**: teacher pay +$5,000 → **+0.86** (CI +0.48/+1.23, the largest identifiable lever); class size −2 → +0.37; turnover −10 → +0.30 (**CI crosses zero**); spending +$2,000 → +0.15 (**crosses zero**); a passed building bond → −0.57 (crosses zero). The large thing is a persistent district effect, **77% unexplained**.
- 🟡 WATCH: Supabase free tier pauses after ~7 days idle → portal shows "database not connected" until woken in dashboard. Vercel Hobby is non-commercial; upgrade both if pursuing revenue.

## Key docs

`AUDIT.md` (all findings) · `DEPLOYMENT.md` (launch runbook) ·
`PROJECT_MAP.md` (visual map) · `docs/ENGINEERING_LOG.md` (session memory).

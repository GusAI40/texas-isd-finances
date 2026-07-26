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
| Live portal | https://texas-isd-finances.vercel.app (Vercel project `texas-isd-finances`, account `tag-ai`) |
| API docs | https://texas-isd-finances.vercel.app/docs |
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
ruff check . && python -m pytest -q       # 36 tests, all must pass
curl -s https://texas-isd-finances.vercel.app/health
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

## Current Status (updated 2026-07-25 — keep this a snapshot, history goes in the log)

- ✅ Live in production, all endpoints verified including end-to-end NLP.
- ✅ Public portal is now the **Texas ISD Financial Resource Guide**: white-minimalist McKinsey/SWD design, penny-of-the-dollar visual, 6 audience lenses, share cards, Methods & citation section, AI disclosure + TAG footer.
- ✅ `static/map.html` ("seating chart" of all 1,202 districts) works on phones — pan/pinch/tap; landmarks + named neighborhoods + plain axes.
- ✅ **"What the money buys" live on every district page** — student need, teacher turnover/experience/salary, STAAR, attendance, graduation, each vs structural peers + state; scored against what demographics predict; statewide lever chart (turnover 10.12% vs spending 0.01%). Data: TEA Snapshot 2009–2024 joined to PEIMS (`scripts/ingest_tea_snapshot.py`, `scripts/build_outcomes_data.py`, `docs/WHAT_A_DOLLAR_BUYS.md`).
- ✅ Guided dollar (hover/tap → peer + state comparison + dollars at stake), zoom ladder, rebuilt landing page with the live statewide dollar, live-figures ticker under the header.
- ✅ Three audit rounds + Monte Carlo audit complete (`AUDIT.md`, `docs/AUDIT_SCORECARD.md`); 32 tests green; CI enforces ruff+pytest.
- 🔴 OPEN: user must rotate credentials pasted into chat on 2026-07-22 (OpenAI/GitHub/Hetzner/Anthropic etc.); OpenAI key in Vercel env needs updating after rotation.
- 🟡 OPEN hardening: read-only DB role for NLP; `/query` needs threadpool+timeout; real rate limiting; analytics; map keyboard/SR path; PR #2 awaiting user review (do not merge).
- 🟡 WATCH: Supabase free tier pauses after ~7 days idle → portal shows "database not connected" until woken in dashboard. Vercel Hobby is non-commercial; upgrade both if pursuing revenue.

## Key docs

`AUDIT.md` (all findings) · `DEPLOYMENT.md` (launch runbook) ·
`PROJECT_MAP.md` (visual map) · `docs/ENGINEERING_LOG.md` (session memory).

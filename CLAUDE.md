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
- **Vercel deploys swap in `requirements-vercel.txt`** as requirements.txt
  (runtime deps incl. NLP; no pandas/matplotlib — bundle cap 500 MB).
- **After any data import**: `REFRESH MATERIALIZED VIEW v_anomaly_flags;`
- Local sandbox note: direct Postgres (port 5432/6543) may be blocked in
  the remote dev container — use the Supabase Management API
  (`POST /v1/projects/{ref}/database/query`) for SQL and PostgREST for bulk
  data, both over HTTPS.

## Verify before claiming anything works

```bash
ruff check . && python -m pytest -q       # 24 tests, all must pass
curl -s https://texas-isd-finances.vercel.app/health
```

## Current Status (updated 2026-07-23 — keep this a snapshot, history goes in the log)

- ✅ Live in production, all endpoints verified including end-to-end NLP.
- ✅ Admin dashboard v3 live: white-minimalist McKinsey/SWD design, action titles, exec summary, MECE breakdown, compare mode, PNG/CSV exports, /query rate limit. Demand-weighted grade ≈3.96/4.0.
- ✅ Three audit rounds complete (`AUDIT.md`); 29 tests green; CI enforces ruff+pytest.
- 🔴 OPEN: user must rotate credentials pasted into chat on 2026-07-22 (OpenAI/GitHub/Hetzner/Anthropic etc.); OpenAI key in Vercel env needs updating after rotation.
- 🟡 WATCH: Supabase free tier pauses after ~7 days idle → portal shows "database not connected" until woken in dashboard. Vercel Hobby is non-commercial; upgrade both if pursuing revenue.

## Key docs

`AUDIT.md` (all findings) · `DEPLOYMENT.md` (launch runbook) ·
`PROJECT_MAP.md` (visual map) · `docs/ENGINEERING_LOG.md` (session memory).

# Architecture

Technical companion to [REPO_MAP.md](REPO_MAP.md) (visual blueprint) and
[PROJECT_MAP.md](PROJECT_MAP.md) (plain-English map). Every statement below
was verified against the code and the live system on 2026-07-23.

## System in one sentence

A FastAPI service (`src/api.py`) serves a zero-build static dashboard
(`static/index.html`) and a JSON API over read-only Postgres views on
Supabase, with an optional LangChain+OpenAI agent (`src/nlp_engine.py`)
that turns plain-English questions into SELECT-only SQL.

## Runtime topology

- **Production:** Vercel Python serverless. `api/index.py` exposes the ASGI
  `app`; `vercel.json` rewrites all routes to it and `excludeFiles` drops
  tests/data from the bundle. Deploys swap `requirements-vercel.txt` in as
  `requirements.txt` (NLP included; pandas/matplotlib excluded — offline
  tooling only).
- **Database:** Supabase Postgres (us-east-1). Serverless connects through
  the **transaction pooler (port 6543)**; `src/api.py` sets asyncpg
  `statement_cache_size=0`, required for pooler compatibility. The direct
  DB host is IPv6-only — never use it from IPv4 hosts.
- **Alternates (configured, unexercised):** `render.yaml` blueprint,
  `Dockerfile` for any VPS.

## Request paths

### Dashboard / data endpoints
```
browser → api/index.py → src/api.py route → asyncpg pool → view → JSON
```
Routes (all in `src/api.py`): `GET /` (dashboard), `/api`, `/districts`,
`/district/{id}/summary`, `/district/{id}/peers`, `/district/{id}/breakdown`,
`/benchmarks`, `/anomalies`, `/stats`, `/sample-queries`, `/health`,
`POST /query`. Interactive docs at `/docs` (FastAPI-generated).

### NLP path
```
POST /query → per-IP rate limit (10/min, QUERY_RATE_LIMIT env)
           → TexasFinanceNLPEngine (lazy singleton)
           → langchain.agents.create_agent + SQLDatabaseToolkit
           → SELECT against v_finance_summary / v_anomaly_flags only
           → answer text
```
Engine guardrails: `include_tables` allowlist (two views), SELECT-only
system prompt (`SYSTEM_PROMPT` in `src/nlp_engine.py`), `recursion_limit`
15, question length bounded 3–500 chars (Pydantic), and database-level
privileges (see Security).

## Data model

- **Base table** `texas_school_finance`: 140 columns straight from TEA's
  Summarized PEIMS Actual Financial Data (fiscal 2009–2025), PK
  `(district_number, year)`. `district_number` is a **6-digit string**
  (leading zeros are significant: `057905` = Dallas ISD).
- **Views** (the only public surface):
  - `v_finance_summary` — core metrics + per-student calculations
    (`sql/create_tables.sql`)
  - `v_anomaly_flags` — **materialized**; YoY flags (revenue drop >15%,
    spend spike >20% w/ flat enrollment, per-student spike >15%,
    enrollment decline >10%) with before/after values. Must be refreshed
    after every import.
  - `v_spending_breakdown` — 9 MECE operating categories grouped from TEA
    function codes (`sql/create_breakdown_view.sql`)

### Data pipeline (manual, once per TEA release)
1. Download the current release from tea.texas.gov (sheet `DATAMART`).
2. `python scripts/prepare_data.py` → `data/texas_finance_clean.csv`
   (zero-pads IDs, snake_cases 140 headers; gitignored).
3. `python scripts/import_to_supabase.py` → creates/fills the table
   (reads with `dtype={"district_number": str}` — do not remove).
4. Run `sql/create_tables.sql` then `sql/create_breakdown_view.sql`
   (import-first order is mandatory: the import defines the 140 columns).
5. `REFRESH MATERIALIZED VIEW v_anomaly_flags;`

Failure mode: pipeline steps are idempotent-by-rerun; a failed import can
be truncated and re-run. There is no automated scheduler — see RUNBOOK.md.

## Security model

- **Least privilege at the database:** base table has RLS enabled with no
  policies and REVOKEd grants for API roles; `anon`/`authenticated` can
  SELECT only the three views (`sql/*.sql`).
- **API surface:** read-only semantics (GET + one POST that only reads);
  parameterized queries throughout; `/anomalies` flag column names come
  from a hardcoded allowlist (`_FLAG_COLUMNS`); CORS restricted to
  GET/POST with configurable origins; no cookies, no sessions, no PII —
  district-level aggregates only.
- **Secrets:** only in Vercel env vars (`SUPABASE_DB_URL`,
  `OPENAI_API_KEY`). Never in the repo; `.gitignore` covers `.env`;
  history was secret-scanned (AUDIT.md R2-3).
- **Cost control:** `/query` rate limit 10/min/IP. Caveat: enforcement is
  per serverless instance (in-process memory); a CDN/WAF layer is the
  recommended hard cap before heavy promotion.
- **No authentication exists** — deliberate for a free public tool;
  becomes the first requirement for any paid tier.

## Frontend architecture

`static/index.html` is a single self-contained file (no framework, no
build). Design system: white-minimalist, storytelling-with-data +
McKinsey principles — action titles computed from live data
(`trendTitle()`, `renderExec()`), executive summary first, gray context /
blue focus, orange reserved for compare mode, direct end-of-line labels,
data tables behind disclosure toggles, print stylesheet, PNG/CSV export
(`pngDownload()`, `csvDownload()`), guided tour (`TOUR`), disclaimer
modal, per-section TEA citations. District choice and tour state persist
in `localStorage` only.

## Quality gates

- `pytest` (29 tests, `tests/`): runs with zero credentials — boot,
  endpoint contracts, 503 degradation, validation bounds, rate limiter,
  NLP agent construction against SQLite (catches LangChain API drift),
  data-prep helpers, chart-library smoke tests.
- `ruff` (config in `pyproject.toml`).
- CI (`.github/workflows/ci.yml`): both, on Python 3.10/3.11/3.12, on
  every push/PR to master. **No type checker is configured** (gap).

## Known constraints & failure behavior

- App boots with no credentials: dashboard + `/docs` + `/health` stay up;
  data endpoints return 503 with instructions; `/health` reports
  `degraded`.
- Supabase free tier pauses after ~7 days idle → `/health` degrades;
  wake in the dashboard (RUNBOOK.md).
- LangChain pin `>=1.0,<2.0`; `langchain-community` (SQL toolkit) is
  sunset upstream but functional — watch its issue #674.
- Dev-container caveat: raw Postgres ports may be blocked; use the
  Supabase Management API / PostgREST over HTTPS (see ENGINEERING_LOG
  2026-07-22).

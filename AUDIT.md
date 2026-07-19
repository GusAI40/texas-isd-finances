# Public-Launch Audit — June 1, 2026

Full code and repository audit performed ahead of opening this project for
public use. Scope: every source file, SQL schema, docs, CI, and git history.

## Summary

The repository history was previously sanitized (credentials removed,
internal planning docs deleted, MIT license and CI added). This audit found
and fixed the following issues that would have prevented or degraded a
public launch.

## Findings and resolutions

### Blocking (app would not start or endpoints crashed)

| # | Finding | Resolution |
|---|---------|------------|
| 1 | `src/api.py` used `from nlp_engine import …`, which fails when the app is launched the documented way (`uvicorn src.api:app`) | Switched to package-relative import |
| 2 | The NLP engine was constructed at import time, so a missing `OPENAI_API_KEY` or `SUPABASE_DB_URL` crashed the whole API — including `/docs` and `/health` | Engine is now lazily initialized; `/query` returns 503 with a clear message until configured |
| 3 | `visualizations.py` called `fig.update_xaxis()` / `fig.update_yaxis()`, which do not exist in Plotly (`AttributeError` on every currency-formatted chart) | Corrected to `update_xaxes()` / `update_yaxes()`; covered by smoke tests |
| 4 | Scatter-plot trendline paired *sorted* y-values with *unsorted* x-values, drawing a meaningless line | Trend now computed over enrollment-ordered data |

### Security / correctness

| # | Finding | Resolution |
|---|---------|------------|
| 5 | CORS was configured with wildcard origins **and** `allow_credentials=True` — an invalid combination browsers reject; methods were also unrestricted | Credentials disabled with wildcard; methods restricted to GET/POST; origins configurable via `CORS_ALLOW_ORIGINS` |
| 6 | `/anomalies` interpolated the flag column name into SQL from the query string (constrained by an enum, but fragile) | Replaced with an explicit whitelist mapping; non-whitelisted values are rejected with 422 |
| 7 | README claimed row-level security, but `sql/create_tables.sql` never enabled it — API roles could read the base table directly | Base table access revoked for `anon`/`authenticated` and RLS enabled; access is via the two public views only |
| 8 | No input bounds on `/query` question length | Bounded 3–500 chars |
| 9 | Deprecated `@app.on_event` startup hooks; DB pool creation would crash the app if the DB was briefly unreachable | Migrated to lifespan handler with graceful degradation (`/health` reports `degraded`) |

### Quality / launch readiness

| # | Finding | Resolution |
|---|---------|------------|
| 10 | No tests; CI linted with `--exit-zero` (never fails) and the "type check" step only printed a version string | Added a pytest suite (API boot, endpoint contracts, data-prep helpers, visualization smoke tests); CI now enforces ruff + pytest on Python 3.10–3.12 |
| 11 | README referenced deleted `implementation_plan.md`; QUICKSTART used Windows-only commands; license section didn't mention MIT | Docs rewritten, cross-platform |
| 12 | No public-facing frontend — only raw JSON endpoints | Added `static/index.html`: a dependency-free portal (district search, spending trend chart, anomaly table, NLP question box) served at `/` |
| 13 | No deployment story | Added `Dockerfile`, `render.yaml` blueprint, Vercel entrypoint, and `DEPLOYMENT.md` |
| 14 | `v_anomaly_flags` is a materialized view with no documented refresh step | Refresh documented in SQL and DEPLOYMENT.md |

## Data currency

Data coverage is TEA's summarized financial data for fiscal years
**2008–2024** (latest release as of this audit). Bounds are configurable via
`DATA_MIN_YEAR` / `DATA_MAX_YEAR` when TEA publishes new years.

## Residual risks (documented, not blocking)

- `/query` invokes a paid LLM per request; add rate limiting before heavy
  public promotion (see DEPLOYMENT.md).
- The NLP agent's SQL access is limited to two read-only views, and the
  schema grants no write access to API roles; still, prefer a dedicated
  read-only database role in production.
- Anomaly thresholds (15/20/10%) are heuristics; the portal labels them as
  starting points for questions, not findings of wrongdoing.

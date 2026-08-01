# Public-Launch Audit — June 1, 2026 (Round 2 addendum below, July 22, 2026)

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
- ~~The NLP agent's SQL access is limited to two read-only views, and the
  schema grants no write access to API roles; still, prefer a dedicated
  read-only database role in production.~~ **Closed.**
  `sql/create_nlp_role.sql` creates `nlp_reader` — SELECT on the two views,
  `default_transaction_read_only = on`, no schema or role rights — and
  `src/nlp_engine.py` prefers `NLP_DB_URL` over the owner connection. The
  point: `include_tables` controlled what the agent was *told about*, never
  what the database would *let it run*. Now the boundary is enforced where
  a prompt cannot reach it. The env-var fallback to `SUPABASE_DB_URL` keeps
  a fresh checkout working, so a deployment is only actually protected once
  `NLP_DB_URL` is set — DEPLOYMENT.md step 1.3.
- Anomaly thresholds (15/20/10%) are heuristics; the portal labels them as
  starting points for questions, not findings of wrongdoing.

---

# Round 2 — Documentation-Validated Audit (July 22, 2026)

Second pass with every assumption checked against current provider
documentation and the installed dependency versions, plus a full git-history
secret scan.

## Findings and resolutions

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| R2-1 | **High** | The NLP engine was written against the removed LangChain legacy API: with current LangChain (1.x, installed 1.3.14) `from langchain.agents import create_sql_agent` raises `ImportError`, so `/query` could never work on a fresh install. The round-1 test suite deliberately avoided importing the module, masking this. | Rewritten on the supported `langchain.agents.create_agent` API; requirements pinned to `langchain>=1.0,<2.0`; new construction tests run the engine against a local SQLite database on every CI run so API drift is caught immediately |
| R2-2 | **High** | `env_template.txt` used Supabase's direct-connection format (`db.[REF].supabase.co:5432`). Per current Supabase docs this host is **IPv6-only** without the paid IPv4 add-on — Render/Railway/Vercel egress over IPv4, so every documented deploy path would have failed with connection timeouts. | Template and DEPLOYMENT.md now lead with the shared **session pooler** string (`postgres.[REF]@aws-[REGION].pooler.supabase.com:5432`), which is IPv4-compatible on all tiers |
| R2-3 | **Medium** | Git-history secret scan: deleted internal status docs remain in history and expose the old Supabase **project ref** (`emtwbizmorqwhboebgzw`) and confirm which services were configured. No complete secrets leak (DB password is masked, the anon key is truncated at the JWT header, no OpenAI keys found). | Documented here. **Recommendation:** if that Supabase project is still live, rotate its database password and anon key, since the ref narrows an attacker's target. History rewrite is optional (refs are semi-public by design) but `git filter-repo` guidance is available if desired |
| R2-4 | Medium | `vercel.json` used `includeFiles`, which the current Vercel Python runtime docs do not support — Python bundles include all project files by default and support only `excludeFiles`. | Replaced with `excludeFiles` for tests/data; docs updated with the current 500 MB uncompressed bundle cap and Python 3.12 default |
| R2-5 | Low | `langchain-community` (source of `SQLDatabase`/`SQLDatabaseToolkit`) was officially sunset in June 2026 and is no longer actively maintained. It still functions and no standalone replacement for the SQL toolkit exists yet. | Documented in code and here; track langchain-community issue #674 for the migration path |
| R2-6 | Low | Dead code: `DistrictSummary`/`AnomalyFlag` Pydantic models were defined but never used. | Removed |
| R2-7 | Info | `render.yaml` validated against the current Blueprint spec: `runtime: python` (correct; `env:` is discouraged), `plan: free`, and `healthCheckPath` are all valid. | No change needed |

## Version matrix validated (July 22, 2026)

| Package | Installed/tested | Notes |
|---|---|---|
| fastapi | 0.139.x | lifespan API current |
| langchain | 1.3.x | `create_agent` is the supported agent API |
| langchain-community | 0.4.x | sunset June 2026; still functional |
| pydantic | 2.13.x | v2 API used throughout |
| asyncpg | 0.31.x | — |
| plotly | 6.9.x | `update_xaxes`/`update_yaxes` verified |
| pandas | 3.0.x | prepare-data helpers tested |

The suite passed against this matrix at the time; CI enforces ruff + pytest on Python
3.10–3.12.

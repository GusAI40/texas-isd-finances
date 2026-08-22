# Deployment Guide — Going Public

This guide takes the project from a fresh clone to a publicly reachable portal.

## Architecture

```
TEA Excel data ──▶ scripts/prepare_data.py ──▶ data/texas_finance_clean.csv
                                                      │
                                                      ▼ scripts/import_to_supabase.py
Supabase (Postgres) ◀──── sql/create_tables.sql (tables, views, RLS, grants)
        │
        ▼
FastAPI (src/api.py) ── serves ──▶ static/index.html  (public portal)
        │                          /docs               (OpenAPI docs)
        ▼
DeepSeek or OpenAI via LangChain (src/nlp_engine.py) — natural-language questions
```

## 1. Provision the database (Supabase)

1. Create a project at https://app.supabase.com (free tier is fine).
2. **Import the data before you run any SQL.** `scripts/import_to_supabase.py`
   creates the base table itself — pandas writes all 140 columns straight from
   the cleaned TEA file. Only then run `sql/create_tables.sql`, which adds the
   primary key, indexes, public views, the anomaly materialized view, RLS and
   grants **to a table that must already exist**. Running the SQL first fails
   with `relation "public.texas_school_finance" does not exist`; the file's own
   header says so, and this step used to say the opposite.

       python scripts/prepare_data.py          # Excel → data/texas_finance_clean.csv
       python scripts/import_to_supabase.py    # creates + fills the table
       # then paste sql/create_tables.sql into the SQL Editor

3. Run `sql/create_nlp_usage.sql`. This is the counter that bounds `/query`'s
   provider calls across every serverless instance. Skipping it does not break
   anything — the API logs a warning and falls back to per-instance counters —
   but per-instance counters are not a ceiling: Vercel starts as many
   instances as traffic demands, so "60 per minute" becomes "60 per minute
   times however many instances an attacker can provoke".
4. Run `sql/create_nlp_role.sql` (after replacing `CHANGE_ME` with a password
   you generate). This creates `nlp_reader`: SELECT on the two public views,
   read-only transactions, schema `USAGE` only, and no CREATE, base-table, or
   public-function rights. `/query` lets a language model
   write its own SQL, so it must not hold the owner connection — the
   least-privilege boundary has to live in the database, where a prompt
   cannot argue with it. The role's pooler URL is your `NLP_DB_URL`.
5. Copy the **connection string** — this is your `SUPABASE_DB_URL`.

   ⚠️ **Use the Session pooler string** (Connect → Session pooler:
   `postgresql://postgres.[REF]:[PASSWORD]@aws-[REGION].pooler.supabase.com:5432/postgres`).
   Per current Supabase docs, the "direct connection" host
   (`db.[REF].supabase.co:5432`) is **IPv6-only** unless you buy the IPv4
   add-on — and Render, Railway, and Vercel egress over IPv4, so the direct
   string will fail there with a connection timeout.

## 2. Load the data

```bash
python -m pip install "uv==0.11.33"
uv sync --locked --all-extras
cp env_template.txt .env        # then edit .env with your credentials

# Place the TEA Excel file in the project root, then:
python scripts/prepare_data.py
python scripts/import_to_supabase.py

# Finally, refresh the anomaly view (SQL Editor):
#   REFRESH MATERIALIZED VIEW public.v_anomaly_flags;
```

The source file is TEA's *2009–2025 Summarized Financial Data* release
(PEIMS), available from the Texas Education Agency website. Re-run these two
scripts and the refresh whenever TEA publishes a new year.

## 3. Deploy the API + portal

The app boots even with no credentials configured (the portal shows a
"database not connected" banner and data endpoints return 503), so you can
deploy first and wire credentials after.

### Option A — Render (simplest, free tier)

The repo contains a `render.yaml` blueprint:

1. https://dashboard.render.com → **New → Blueprint** → point it at this repo.
2. Set `SUPABASE_DB_URL`, `NLP_DB_URL`, `NLP_PROVIDER=deepseek`, and
   `DEEPSEEK_API_KEY` when prompted. To select OpenAI instead, set
   `NLP_PROVIDER=openai` and `OPENAI_API_KEY`.
3. Render builds and serves the portal at `https://<service>.onrender.com`.

### Option B — Docker (Railway, Fly.io, any VPS)

```bash
docker build -t texas-isd-finances .
docker run -p 8000:8000 \
  -e SUPABASE_DB_URL="postgresql://..." \
  -e NLP_DB_URL="postgresql://nlp_reader..." \
  -e NLP_PROVIDER="deepseek" \
  -e DEEPSEEK_API_KEY="..." \
  texas-isd-finances
```

### Option C — Vercel (the current production deployment)

The current production path is Vercel's Git integration from `master`.
`.github/workflows/deploy.yml` does not deploy and holds no Vercel secrets: it
waits for the Git-driven deployment to serve the matching revision with a
healthy database and `tracking_schema=ready`, then runs strict live
verification. Schema readiness means startup observed all three application
sentinels, the current journey-view marker, and the cron-log privacy constraint
when `cron_runs` exists (a missing optional cron table is treated as safe). It
is a startup gate, not a continuous audit of database grants. A manual CLI
deploy is an emergency operator path only; disconnect Git integration before
making it authoritative. Never let two deploy mechanisms race for the alias.

`vercel.json` and `api/index.py` are included; Vercel's Python runtime
auto-detects the ASGI `app` (Python 3.12 by default). Python bundles are
capped at **500 MB uncompressed** and include all project files by default
(`.vercelignore` drops tests and offline data, with explicit re-includes for
runtime files that live under otherwise excluded paths).

Vercel resolves the base `[project]` dependencies from `pyproject.toml` and
the committed universal `uv.lock`. Do not swap requirement files into the
deploy payload. The `offline` and `server` extras stay out of the function
bundle, while the base runtime still includes the full API and `/query`.

Before any deploy, run `uv lock --check`. Dependency updates are made by
editing `pyproject.toml`, regenerating `uv.lock` with the reviewed uv version,
and passing CI; production must never resolve a new dependency graph merely
because an upstream package was published.

In Vercel project settings, set `SUPABASE_DB_URL`, `NLP_DB_URL`, and the key
for the selected model provider. Use the **transaction pooler** connection
string (port 6543) — the API disables asyncpg's statement cache so it is
pooler-compatible. Configure cron/outreach variables separately for those
operations; repository documentation is not proof that any value exists.

## 4. Configuration reference

| Variable | Required | Purpose |
|---|---|---|
| `SUPABASE_DB_URL` | for data endpoints | Postgres connection string (owner) |
| `NLP_DB_URL` | for `/query` | Required least-privilege `nlp_reader` connection. If unset, `/query` is unavailable; model-authored SQL never falls back to the owner. |
| `DEEPSEEK_API_KEY` | for `/query` (DeepSeek) | Used when DeepSeek is selected. With no explicit provider, its presence selects DeepSeek. |
| `OPENAI_API_KEY` | for `/query` (OpenAI) | Used when OpenAI is selected. With no explicit provider and no DeepSeek key, OpenAI is selected. |
| `NLP_PROVIDER` | no (auto) | Explicitly select `deepseek` or `openai`; the selected provider's key must exist. |
| `CORS_ALLOW_ORIGINS` | no (default `*`) | Comma-separated allowed origins |
| `NLP_MODEL` | no (per provider) | Model id. Defaults: `deepseek-v4-flash` / `gpt-4o-mini` |
| `NLP_BASE_URL` | no (per provider) | Override the API endpoint |
| `NLP_TEMPERATURE` | no (default `0`) | Determinism for SQL generation |
| `NLP_VERBOSE` | no (default `false`) | Log agent reasoning |
| `DATA_MIN_YEAR` / `DATA_MAX_YEAR` | no (2009/2025) | Data coverage bounds |
| `QUERY_RATE_LIMIT` | no (default 10) | `/query` per IP, per minute. Per-process; spoofable via `X-Forwarded-For`, so this only stops one honest user hogging the box. |
| `QUERY_GLOBAL_LIMIT` | no (default 60) | `/query` all callers, per minute. Counted in the database, so it holds across every instance. |
| `QUERY_DAILY_LIMIT` | no (default 5000) | `/query` all callers, per day. **This is the one that bounds the bill** — a per-minute cap alone still permits 86,400 calls a day. |
| `SITE_PASSWORD` | no (unset = public) | Locks the **whole site** behind a browser password prompt. See below. |
| `SITE_USERNAME` | no (default `txisd`) | Username for that prompt; the password is what actually gates. |
| `CRON_SECRET` | for Vercel cron routes | Bearer secret for `/api/cron/*`; Vercel cron and the application must share it. |
| `RESEND_API_KEY` | to send outreach | Resend credential used by the server runner and delivery/KPI tooling. |
| `RESEND_FROM` / `RESEND_REPLY_TO` / `TAG_BCC` | no | Sender, reply, and private-copy routing overrides. |
| `TAG_POSTAL_ADDRESS` | to arm outreach | Business postal address intentionally included in outbound mail for compliance; never copy it into logs or public telemetry. |
| `OUTREACH_TOKEN` / `OPS_TOKEN` | for private operator routes | Separate bearer credentials for outreach control and operational status. |
| `IMAP_USER` / `IMAP_PASSWORD` / `IMAP_HOST` | for reply ingestion | Mailbox identity, app password, and optional host used by the reply job. |
| `SUPABASE_PAT` | for management jobs | Supabase Management API credential for local synchronization, reply, and KPI scripts; not the normal request-path database credential. |
| `VERCEL_GIT_COMMIT_SHA` | for production verification | Non-secret Vercel system value returned as `/health.revision`. Enable exposure of Vercel System Environment Variables to the function; otherwise the API reports `local` and strict verification fails. |

### Choosing the language model (DeepSeek or OpenAI)

`/query` and the optional news enrichment both read one config
(`src/llm_config.py`), so they can never split across two providers and bill
two accounts.

**To run on DeepSeek**, set `DEEPSEEK_API_KEY` in the TAG-ai Vercel project's
Production environment, then use the Vercel dashboard to redeploy the latest
Production deployment whose source is the verified current `master` commit.
Keep Git integration authoritative; do not create a second CLI deployment.
After the redeploy, verify both the tree and the NLP path:

```bash
git fetch origin master
python scripts/verify_live.py --require-network \
  --expect-revision "$(git rev-parse origin/master)" --with-query
```

**To go back to OpenAI**, remove `DEEPSEEK_API_KEY` (or set
`NLP_PROVIDER=openai`) in the project environment and repeat that same
Git-integrated dashboard redeploy and strict verification.

DeepSeek implements the OpenAI request format — including the tool-calling the
SQL agent depends on — so only the base URL (`https://api.deepseek.com`) and
the model name change. Nothing else in the pipeline is provider-specific.

DeepSeek pricing varies by model, cache state, and peak/off-peak period. Check
the provider's [current official pricing](https://api-docs.deepseek.com/quick_start/pricing)
before changing models or budgets; do not copy a historical price comparison
into an operating decision. `deepseek-v4-pro` remains selectable with
`NLP_MODEL` when a harder-query model is intentionally chosen.

`/health` reports the live provider and model, so a switch can be confirmed
from outside without reading environment variables. It never echoes the key.

### Locking the site for a private preview

Setting `SITE_PASSWORD` turns the portal into a private preview — every page
and API route returns `401` with a browser login prompt until the password is
entered. Useful before a launch, or while showing the site to a few people.

Add `SITE_PASSWORD` to the TAG-ai Vercel project's Production environment,
then use the dashboard to redeploy the latest Production deployment sourced
from verified current `master`. Confirm its source revision before redeploying.

**To make the site public again — the state a transparency portal should
normally be in — remove the variable in the project environment and repeat the
same Git-integrated dashboard redeploy.** In both directions, run the strict
revision/health verification above after the alias changes.

Two route groups stay open while locked, by design:

- **`/health`** — so uptime monitoring does not alarm over a deliberate lock.
- **`/api/cron/*`** — both the intelligence refresh and outreach drain carry
  their own `CRON_SECRET` bearer. Without this exemption scheduled operations
  would silently stop while the site is locked. They still refuse a wrong
  secret.

Neither reveals district data. Locked responses are sent `no-store` and
`X-Robots-Tag: noindex`, so a preview is never cached or indexed. The password
lives only in the environment — never in the repo, so it rotates without a code
change and never enters git history.

**Security notes for public operation**

- Point model-authored SQL at the dedicated **read-only** `nlp_reader` role
  through `NLP_DB_URL`; `/query` refuses to initialize without it and never
  falls back to the database-owner `SUPABASE_DB_URL`. The SQL role remains the
  final boundary even though the application also permits only two public
  finance views.
- `/query` calls the configured paid LLM API. `QUERY_GLOBAL_LIMIT` and
  `QUERY_DAILY_LIMIT` are counted in `public.nlp_usage`, so they hold across
  every serverless instance rather than per-process — but they cap the number
  of CALLS, not dollars. Configure a provider-side spend limit or prepaid
  balance too; application call counters cannot price a call.
- Never commit `.env`; both `.gitignore` and this repo's history are clean.

## 5. Verify the launch

```bash
curl https://<your-host>/health
# Require: status=healthy, database=connected, tracking_schema=ready,
# the expected 40-character revision, and the intended sanitized llm value.
python scripts/verify_live.py --require-network \
  --base-url https://<your-host> --expect-revision <40-character-git-sha>
curl https://<your-host>/stats
curl "https://<your-host>/districts?search=Dallas"
```

Then open `https://<your-host>/` in a browser — the portal should show
statewide stats, district search, and recent anomaly flags.

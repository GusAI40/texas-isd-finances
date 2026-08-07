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
OpenAI via LangChain (src/nlp_engine.py) — natural-language questions
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
   OpenAI spend across every serverless instance. Skipping it does not break
   anything — the API logs a warning and falls back to per-instance counters —
   but per-instance counters are not a ceiling: Vercel starts as many
   instances as traffic demands, so "60 per minute" becomes "60 per minute
   times however many instances an attacker can provoke".
4. Run `sql/create_nlp_role.sql` (after replacing `CHANGE_ME` with a password
   you generate). This creates `nlp_reader`: SELECT on the two public views,
   read-only transactions, no schema rights. `/query` lets a language model
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
pip install -r requirements.txt
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
2. Set `SUPABASE_DB_URL` and `OPENAI_API_KEY` when prompted.
3. Render builds and serves the portal at `https://<service>.onrender.com`.

### Option B — Docker (Railway, Fly.io, any VPS)

```bash
docker build -t texas-isd-finances .
docker run -p 8000:8000 \
  -e SUPABASE_DB_URL="postgresql://..." \
  -e OPENAI_API_KEY="sk-..." \
  texas-isd-finances
```

### Option C — Vercel (the current production deployment)

`vercel.json` and `api/index.py` are included; Vercel's Python runtime
auto-detects the ASGI `app` (Python 3.12 by default). Python bundles are
capped at **500 MB uncompressed** and include all project files by default
(`excludeFiles` in `vercel.json` already drops tests and data).

Deploy with `requirements-vercel.txt` as the deployment's `requirements.txt`
— the full API **including NLP** with only the offline data-prep/viz
libraries removed. Everything works on this target: portal, districts,
anomalies, stats, and `/query`.

Set the same two environment variables in the Vercel project settings and
use the **transaction pooler** connection string (port 6543) — the API
disables asyncpg's statement cache so it is pooler-compatible.

## 4. Configuration reference

| Variable | Required | Purpose |
|---|---|---|
| `SUPABASE_DB_URL` | for data endpoints | Postgres connection string (owner) |
| `NLP_DB_URL` | for `/query` | Least-privilege `nlp_reader` connection. Falls back to `SUPABASE_DB_URL` if unset — that works, but runs model-authored SQL as the owner. Set it. |
| `OPENAI_API_KEY` | for `/query` | LLM for natural-language questions |
| `CORS_ALLOW_ORIGINS` | no (default `*`) | Comma-separated allowed origins |
| `NLP_MODEL` | no (default `gpt-4o-mini`) | OpenAI model for NLP queries |
| `NLP_VERBOSE` | no (default `false`) | Log agent reasoning |
| `DATA_MIN_YEAR` / `DATA_MAX_YEAR` | no (2009/2025) | Data coverage bounds |
| `QUERY_RATE_LIMIT` | no (default 10) | `/query` per IP, per minute. Per-process; spoofable via `X-Forwarded-For`, so this only stops one honest user hogging the box. |
| `QUERY_GLOBAL_LIMIT` | no (default 60) | `/query` all callers, per minute. Counted in the database, so it holds across every instance. |
| `QUERY_DAILY_LIMIT` | no (default 5000) | `/query` all callers, per day. **This is the one that bounds the bill** — a per-minute cap alone still permits 86,400 calls a day. |
| `SITE_PASSWORD` | no (unset = public) | Locks the **whole site** behind a browser password prompt. See below. |
| `SITE_USERNAME` | no (default `txisd`) | Username for that prompt; the password is what actually gates. |

### Locking the site for a private preview

Setting `SITE_PASSWORD` turns the portal into a private preview — every page
and API route returns `401` with a browser login prompt until the password is
entered. Useful before a launch, or while showing the site to a few people.

```bash
vercel env add SITE_PASSWORD production --scope tag-ai-projects
vercel deploy --prod --scope tag-ai-projects        # env is baked at deploy time
```

**To make the site public again — the state a transparency portal should
normally be in — remove the variable and redeploy:**

```bash
vercel env rm SITE_PASSWORD production --scope tag-ai-projects
vercel deploy --prod --scope tag-ai-projects
```

Two paths stay open while locked, by design:

- **`/health`** — so uptime monitoring does not alarm over a deliberate lock.
- **`/api/cron/isd-intelligence`** — the daily news run, which carries its own
  `CRON_SECRET` bearer. Without this exemption the feed would silently stop
  updating for as long as the lock is on. It still refuses a wrong secret.

Neither reveals district data. Locked responses are sent `no-store` and
`X-Robots-Tag: noindex`, so a preview is never cached or indexed. The password
lives only in the environment — never in the repo, so it rotates without a code
change and never enters git history.

**Security notes for public operation**

- Point the API at a **read-only** database role where possible
  (`SUPABASE_READONLY_URL` pattern in `env_template.txt`); the NLP agent can
  only see the two public views either way.
- `/query` calls a paid OpenAI API. `QUERY_GLOBAL_LIMIT` and
  `QUERY_DAILY_LIMIT` are counted in `public.nlp_usage`, so they hold across
  every serverless instance rather than per-process — but they cap the number
  of CALLS, not dollars. Set a monthly usage limit on the OpenAI account too;
  that is the only control that can price a call.
- Never commit `.env`; both `.gitignore` and this repo's history are clean.

## 5. Verify the launch

```bash
curl https://<your-host>/health        # {"status":"healthy","database":"connected"}
curl https://<your-host>/stats
curl "https://<your-host>/districts?search=Dallas"
```

Then open `https://<your-host>/` in a browser — the portal should show
statewide stats, district search, and recent anomaly flags.

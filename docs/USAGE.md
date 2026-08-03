# How to use this repo

Written for someone who has just cloned it. Start at the tier you need — each
one adds credentials, and you can stop at any of them.

| Tier | What you need | What you get |
|---|---|---|
| **1 — Read it** | nothing | The whole report: portal, both maps, and every district's outcomes, economics, bonds, equity and the Houston takeover analysis |
| **2 — Live finance data** | a Supabase database | Per-year budgets, peers, anomalies, spending trend, statewide medians |
| **3 — Ask questions** | an OpenAI key | The plain-English question box at `/query` |

---

## Tier 1 — run it with no credentials at all

```bash
pip install -r requirements.txt
uvicorn src.api:app --reload --port 8000
```

Open <http://localhost:8000/>. That is not a degraded mode — 20 of the 32
endpoints are served from committed JSON in `static/` and never touch a
database. The finance layer is the only thing missing, and the page says so
rather than breaking.

Also worth opening: `/geomap` (real district boundaries), `/map` (the
similarity "seating chart"), and `/docs` (interactive OpenAPI).

## Tier 2 — add the finance database

**The order is not interchangeable.** `import_to_supabase.py` *creates* the
base table — pandas writes all 140 columns straight from the cleaned TEA
file. `sql/create_tables.sql` only *decorates* that table with a primary key,
indexes, views, RLS and grants. Run the SQL first and it fails with
`relation "public.texas_school_finance" does not exist`.

```bash
cp env_template.txt .env          # then fill in SUPABASE_DB_URL

# 1. Excel → clean CSV. Download the TEA "Summarized PEIMS Actual Financial
#    Data" release first; the script prints the link if you forget.
python scripts/prepare_data.py path/to/tea-release.xlsx

# 2. Creates AND fills public.texas_school_finance
python scripts/import_to_supabase.py

# 3. NOW run sql/create_tables.sql in the Supabase SQL editor

# 4. After every import, without exception:
#    REFRESH MATERIALIZED VIEW public.v_anomaly_flags;
```

Use the **pooler** connection string, not the direct host — the direct host
(`db.<ref>.supabase.co`) is IPv6-only without a paid add-on, and every common
deploy target egresses over IPv4. Serverless wants transaction mode, port
**6543**; the API sets asyncpg `statement_cache_size=0` to survive it.

## Tier 3 — add natural-language questions

Set `OPENAI_API_KEY`, and set `NLP_DB_URL` **as well**:

```bash
python scripts/apply_nlp_role.py        # needs SUPABASE_PAT + VERCEL_TOKEN
# or by hand: run sql/create_nlp_role.sql, then set NLP_DB_URL
```

Also run `sql/create_nlp_usage.sql`. That table is the call ceiling shared by
every instance — `QUERY_GLOBAL_LIMIT` per minute and `QUERY_DAILY_LIMIT` per
day. Without it the API falls back to per-process counters, which on
serverless is not a ceiling: the platform starts as many instances as traffic
demands, so each one enforces its own separate limit. It caps calls, not
dollars, so set a monthly usage limit on the OpenAI account as well.

This matters more than it looks. `/query` hands a visitor's question to a
language model that writes its own SQL. Limiting the tables the agent is
*told about* does not limit what the connection is *allowed to run* — probed
live, an instruction override made it run `SELECT current_user` (it answered
`postgres`) and read Supabase's `auth` schema. `nlp_reader` can read the two
public views and nothing else, so the injection still works and returns
nothing that isn't already on the page. Without `NLP_DB_URL` the engine falls
back to the owner connection. See `docs/AUDIT_2026-07-31.md` C-1.

---

## Endpoints

Generated from `src/api.py`. "DB" means it needs Tier 2; "static" means it
works at Tier 1.

| Endpoint | Needs | What it returns |
|---|---|---|
| `GET /` | static | The portal page |
| `GET /api` | static | Endpoint directory |
| `POST /query` | *Tier 3* | Plain-English question → answer |
| `GET /health` | static | `healthy` / `degraded` + database state |
| `GET /district/{n}/outcomes` | static | What the money buys: workforce, STAAR, attendance, graduation |
| `GET /district/{n}/economics` | static | What you pay, where it goes, what it bought, who does better |
| `GET /economics/texas` | static | The statewide series behind every district page |
| `GET /district/{n}/bonds` | static | Every bond this district put on a ballot, and the vote |
| `GET /bonds/texas` | static | 66 years of Texas school bond elections |
| `GET /district/{n}/equity` | static | How the district does for the students it actually serves |
| `GET /equity/texas` | static | Statewide results by student group |
| `GET /takeover/houston` | static | Did the 2023 state takeover change results? |
| `GET /fallback-index` | static | District picker + statewide snapshot, for when the DB is down |
| `GET /district-geo` | static | Census TIGER boundaries joined to TEA numbers |
| `GET /map-data` | static | Precomputed similarity-map coordinates |
| `GET /map`, `/geomap` | static | The two map pages |
| `GET /robots.txt`, `/sitemap.xml` | static | Every district is a findable page |
| `GET /sample-queries` | static | Example questions for `/query` |
| `GET /districts` | **DB** | District list / search |
| `GET /district/{n}/summary` | **DB** | Per-year finance rows |
| `GET /district/{n}/peers` | **DB** | Structural peers + statewide percentile |
| `GET /district/{n}/breakdown` | **DB** | Function-level spending |
| `GET /district/{n}/dollar` | **DB** | Where one dollar goes, as 100 pennies |
| `GET /dollar/texas` | **DB** | The whole state's dollar, pooled |
| `GET /district/{n}/turnarounds` | **DB** | Peers that reversed a decline |
| `GET /district/{n}/insights` | **DB** | Where this district materially differs from peers |
| `GET /district/{n}/spending-detail` | **DB** | Object and program spending dimensions |
| `GET /benchmarks` | **DB** | Statewide per-year medians |
| `GET /anomalies` | **DB** | Heuristic flags — questions, not findings |
| `GET /stats` | **DB** | Row/district/year counts |

`{n}` is a **6-digit string** — `057905` is Dallas ISD. Leading zeros are
load-bearing; any pandas read needs `dtype={"district_number": str}`.

Note `/districts?limit=N` returns the first N **alphabetically**, not a
sample. Never resolve a district by scanning it.

---

## Rebuilding the data layers

Each analytical layer is one script producing one committed JSON in
`static/`. After a new TEA release:

```bash
python scripts/ingest_tea_snapshot.py --download
python scripts/build_outcomes_data.py      # must run before build_district_geo
python scripts/build_district_geo.py       # merges the outcomes measures in
python scripts/build_economics_data.py
python scripts/build_bond_data.py
python scripts/build_equity_data.py
python scripts/build_takeover_data.py
python scripts/build_fallback_index.py --from-live   # LAST — it reads the others
```

Those JSON files are build artifacts **and** committed source. The API serves
them directly, which is what makes Tier 1 work. `.vercelignore` must never
exclude `static/`.

## Verifying a change

```bash
ruff check . && python -m pytest -q
python scripts/check_static_js.py
```

That third command is not optional garnish. A `const` redeclaration once
killed `static/map.html` outright while the page still returned 200 and still
contained every string you would grep for. **A 200 proves nothing and
grepping the HTML proves less** — parse the script.

## Deploying

`DEPLOYMENT.md` has the full runbook. Two things that have each cost a
production outage:

- **`vercel.json` must contain no `rewrites` block.** Vercel changed
  backend-framework routing so an internal rewrite passes the *destination*
  path to the app — the old `/(.*) → /api/index` rule made FastAPI receive
  `/api/index` for every request and 404 the entire site while the build
  still reported READY.
- **Production is deployed from a working tree by the CLI, not built from
  `master`.** So `master` can be far behind what is live, and a Vercel
  *redeploy* reuses the old deployment's code — it cannot pick up a code
  change. Ship with a fresh `vercel deploy --prod --scope tag-ai-projects`.

## Where to read next

| Doc | For |
|---|---|
| `docs/PLAIN_ENGLISH.md` | What this is and what it found — no jargon, no background needed |
| `PROJECT_MAP.md` | Visual map of the whole system |
| `docs/TUTORIAL.md` | What each section of the site means |
| `docs/WHAT_A_DOLLAR_BUYS.md` | The methods, and the limits — read before citing |
| `docs/AUDIT_2026-07-31.md` | Security audit; C-1 and how it was closed |
| `docs/ENGINEERING_LOG.md` | Session-by-session history |
| `CLAUDE.md` | The invariants that break production when violated |

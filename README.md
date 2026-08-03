# Texas ISD Financial Data Portal

Where Texas school district money comes from, where it goes, and what it
bought — built from the state's own records, fiscal 2009–2025.

🌐 **Live:** https://txisd.dev

| If you are… | Start here |
|---|---|
| a parent, taxpayer or board member | **[docs/PLAIN_ENGLISH.md](docs/PLAIN_ENGLISH.md)** — what this is and what it found, no jargon |
| here to run or extend the code | **[docs/USAGE.md](docs/USAGE.md)** — the complete guide, including every endpoint |
| trying to picture the system | [PROJECT_MAP.md](PROJECT_MAP.md) — visual map |
| deploying it | [DEPLOYMENT.md](DEPLOYMENT.md) — full runbook |

---

## Run it in 30 seconds

No credentials. No database. Nothing to configure.

```bash
pip install -r requirements.txt
uvicorn src.api:app --reload --port 8000
# open http://localhost:8000/
```

**That is not a demo mode.** 20 of the 32 endpoints are served from committed
JSON in `static/` and never touch a database, so you get the whole report:
every district's results, economics, bonds, equity, the Houston takeover
analysis, and both maps. Only the live finance layer is missing, and the page
says so instead of breaking.

Worth opening too: `/geomap` (real district boundaries), `/map` (the
similarity "seating chart"), `/docs` (interactive API).

## Three tiers

| Tier | Add | Unlocks |
|---|---|---|
| **1** | nothing | The full report — 20 of the 32 endpoints |
| **2** | a Supabase database | Per-year budgets, peers, anomalies, trends, statewide medians |
| **3** | an OpenAI key + `NLP_DB_URL` | The plain-English question box at `/query` |

### Tier 2 — add the finance database

⚠️ **Import first, then run the SQL.** `import_to_supabase.py` *creates* the
table (pandas writes all 140 columns). `sql/create_tables.sql` only *decorates*
it with a primary key, indexes, views, RLS and grants. Run the SQL first and it
fails with `relation "public.texas_school_finance" does not exist`.

```bash
cp env_template.txt .env        # fill in SUPABASE_DB_URL (use the POOLER string)

python scripts/prepare_data.py path/to/tea-release.xlsx   # Excel → clean CSV
python scripts/import_to_supabase.py                      # creates + fills the table
# now paste sql/create_tables.sql into the Supabase SQL editor
# then: REFRESH MATERIALIZED VIEW public.v_anomaly_flags;
```

Use the **pooler** connection string. The direct host is IPv6-only without a
paid add-on, and Vercel/Render/Railway all egress over IPv4.

### Tier 3 — add natural-language questions

```bash
python scripts/apply_nlp_role.py    # creates nlp_reader, wires it up, verifies it
# by hand: run sql/create_nlp_role.sql + sql/create_nlp_usage.sql, set NLP_DB_URL
```

Set `OPENAI_API_KEY` **and** `NLP_DB_URL`. The second one matters: `/query`
hands a visitor's question to a language model that writes its own SQL, and
limiting the tables it is *told about* does not limit what the connection is
*allowed to run*. Without `NLP_DB_URL` that runs as the database owner. See
[docs/AUDIT_2026-07-31.md](docs/AUDIT_2026-07-31.md) C-1 for what that looked
like in practice.

## Endpoints

32 in total — the full table with per-endpoint notes is in
[docs/USAGE.md](docs/USAGE.md#endpoints), and `/docs` serves interactive
OpenAPI. The shape:

**No database needed** — `/`, `/district/{n}/outcomes`, `/economics/texas`,
`/district/{n}/economics`, `/district/{n}/bonds`, `/bonds/texas`,
`/district/{n}/equity`, `/equity/texas`, `/takeover/houston`, `/district-geo`,
`/map`, `/geomap`, `/map-data`, `/fallback-index`, `/sample-queries`,
`/robots.txt`, `/sitemap.xml`, `/api`, `/health`

**Database needed** — `/districts`, `/district/{n}/summary`, `/peers`,
`/breakdown`, `/dollar`, `/dollar/texas`, `/turnarounds`, `/insights`,
`/spending-detail`, `/benchmarks`, `/anomalies`, `/stats`

`{n}` is a **6-digit string** — `057905` is Dallas ISD. Leading zeros are
load-bearing; any pandas read needs `dtype={"district_number": str}`.

## Layout

```
texas-isd-finances/
├── api/index.py            # Vercel entrypoint (no rewrites in vercel.json — see below)
├── src/
│   ├── api.py              # FastAPI: serves the portal, the pages and all 32 endpoints
│   ├── nlp_engine.py       # Plain English → SQL (LangChain 1.x); prefers NLP_DB_URL
│   └── visualizations.py   # Offline chart helpers
├── static/                 # The site AND its data — committed together on purpose
│   ├── index.html          # The portal (single file, no build step)
│   ├── map.html geomap.html
│   └── *.json              # outcomes · economics · bonds · equity · takeover ·
│                           #   district_geo · map_data · fallback_index
├── scripts/                # One script per data layer, each → one committed JSON
│   ├── prepare_data.py import_to_supabase.py
│   ├── ingest_*.py         # TEA snapshot, STAAR, property/tax
│   ├── build_*.py          # outcomes, geo, economics, bonds, equity, takeover, fallback
│   ├── apply_nlp_role.py   # closes audit finding C-1 end to end
│   └── check_static_js.py  # parses the page JS — a 200 response proves nothing
├── sql/                    # create_tables · create_nlp_role · create_nlp_usage · views
├── tests/                  # Runs with no credentials at all
└── docs/                   # PLAIN_ENGLISH · USAGE · TUTORIAL · WHAT_A_DOLLAR_BUYS ·
                            #   AUDIT_2026-07-31 · ENGINEERING_LOG
```

The JSON files in `static/` are build artifacts **and** committed source. The
API serves them directly, which is exactly what makes Tier 1 work.
`.vercelignore` must never exclude `static/`.

## Rebuilding the data after a TEA release

```bash
python scripts/ingest_tea_snapshot.py --download
python scripts/build_outcomes_data.py       # before build_district_geo
python scripts/build_district_geo.py        # merges the outcomes measures in
python scripts/build_economics_data.py
python scripts/build_bond_data.py
python scripts/build_equity_data.py
python scripts/build_takeover_data.py
python scripts/build_fallback_index.py --from-live   # LAST — reads the others
```

## Developing

```bash
pip install -r requirements-dev.txt
ruff check . && pytest
python scripts/check_static_js.py
```

That third command is not garnish. A `const` redeclaration once killed
`static/map.html` outright while the page still returned 200 and still
contained every string you would grep for. **A 200 proves nothing; grepping
the served HTML proves less.** Parse the script. CI runs all three on every
branch.

## What the data says

Short version, with the uncertainty kept in:

- **Spending more does not clearly move test scores.** The measured effect is
  small enough that we cannot rule out zero.
- **Teacher pay is the clearest lever we found** — about +0.9 points per
  $5,000. Still small.
- **About three quarters of the difference between districts is unexplained**
  by anything the state publishes.
- **Passing a building bond shows no clear effect on results.**

Methods, confidence intervals and limits: [docs/WHAT_A_DOLLAR_BUYS.md](docs/WHAT_A_DOLLAR_BUYS.md).
Read that before citing any of it.

## Security

- `/query` runs as **`nlp_reader`** — SELECT on two public views, read-only
  transactions, no schema rights. It is prompt-injectable and that is now
  harmless: everything it can reach is already on the page.
- `QUERY_GLOBAL_LIMIT` and `QUERY_DAILY_LIMIT` are counted **in the database**,
  so they hold across every serverless instance rather than per-process. They
  cap calls, not dollars — set a monthly cap on the OpenAI account too.
- Row-level security on the base table; API roles read only the views.
- Security headers set by the app, so they survive the deploy target.
- No credentials in the repo. Ever. Host environment variables only.

Full findings and how each was verified:
[docs/AUDIT_2026-07-31.md](docs/AUDIT_2026-07-31.md).

## Deploying

[DEPLOYMENT.md](DEPLOYMENT.md) has the runbook for Render, Docker and Vercel.
Two things that have each cost a production outage:

- **`vercel.json` must contain no `rewrites` block.** Vercel changed
  backend-framework routing so an internal rewrite passes the *destination*
  path to the app — the old rule made FastAPI receive `/api/index` for every
  request and 404 the entire site while the build still reported READY.
- **Production is deployed from a working tree by the CLI, not built from
  `master`.** So `master` can sit far behind what is live, and a Vercel
  *redeploy* reuses the old deployment's code — it cannot pick up a change.

## License

[MIT](LICENSE). Free to use, modify and redistribute. This exists to make
Texas school funding legible to the people paying for it.

Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). This project is
independent — not a TEA product, and it does not rank, recommend or endorse
any district.

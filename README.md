# Texas ISD Financial Data Portal

Where Texas school district money comes from, where it goes, and what it
bought — built from the state's own records, fiscal 2009–2025.

🌐 **Live:** https://txisd.dev

**The problem it solves.** Texas publishes everything about its 1,310 school
districts — finances, results, bonds, debt, tax rates, boundaries — across ten
incompatible files that never talk to each other. So the people paying for it
cannot see the whole picture without a records request and a spreadsheet. This
joins the files, and links every published figure back to the government file
it came from, so a sceptic can check it rather than trust it.

**For** parents, taxpayers, board members, superintendents, journalists and
researchers. Independent — not a TEA product, and it does not rank, recommend
or endorse any district.

**If something looks broken**, jump to
[When something goes wrong](#when-something-goes-wrong).

| If you are… | Start here |
|---|---|
| a parent, taxpayer or board member | **[docs/PLAIN_ENGLISH.md](docs/PLAIN_ENGLISH.md)** — what this is and what it found, no jargon |
| here to run or extend the code | **[docs/USAGE.md](docs/USAGE.md)** — setup and the core endpoint guide; `/docs` is the live API contract |
| trying to picture the system | [PROJECT_MAP.md](PROJECT_MAP.md) — visual map |
| looking for a specific number or field | **[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)** — every file, all 617 fields, generated from the real data |
| asking "can it answer X?" | [docs/COVERAGE_SIMULATION_2026-08-23.md](docs/COVERAGE_SIMULATION_2026-08-23.md) — 82.2% measured, and what the other 18% needs |
| auditing the stack or choosing Agent Skills | [docs/TECH_STACK_AND_AGENT_SKILLS.md](docs/TECH_STACK_AND_AGENT_SKILLS.md) — evidence-backed inventory, official sources, and adoption rules |
| deploying it | [DEPLOYMENT.md](DEPLOYMENT.md) — full runbook |

---

## Current status (2026-08-26)

- **Public application:** live at <https://txisd.dev>. The portal, 53
  database-free report routes, 21 database-backed routes, the MCP server and
  the configured natural-language query path all deploy from `master`.
- **Delivery:** Vercel Git integration owns production. Every merge is checked
  against the exact deployed Git revision, database health, startup-managed
  schema markers, and the live API contract (`scripts/verify_live.py`).
- **Answerability, measured:** a 90-day Monte Carlo over 60,042 realistic
  inquiries puts the portal at **82.2%** fully answerable from the data it
  actually holds (95% CI 82.0–82.4). Method, per-category grades and the honest
  ceiling: [docs/COVERAGE_SIMULATION_2026-08-23.md](docs/COVERAGE_SIMULATION_2026-08-23.md).
  A separate weekly job holds the live agent to an accuracy floor.
- **Known operator hold:** outbound outreach is fail-closed and **unarmed**.
  Verify for yourself — `curl -s 'https://txisd.dev/api/cron/runs?job=outreach-drain'`
  reports `skipped` / `unarmed` on every firing. It stays that way until the
  owner sets `RESEND_API_KEY`, `TAG_POSTAL_ADDRESS` and `OUTREACH_TOKEN` in the
  deploy platform. **This exposes no addresses and does not affect the public
  finance portal.** Never send this outreach by any path other than the queue —
  a direct provider call bypasses the `UNIQUE(email)` guard, the committed
  watermark, the identity gate, opt-outs and the sent log.
- **Also owed by the owner:** a provider-side spend ceiling on the LLM account.
  The in-app meters bound calls and tokens; only the provider bounds dollars.
- **Source of truth:** current code and docs live on
  [`master`](https://github.com/GusAI40/texas-isd-finances/tree/master); old
  audit and feature branches are not operating documentation.

## Run it in 30 seconds

No credentials. No database. Nothing to configure.

```bash
python -m pip install "uv==0.11.33"
uv sync --locked --no-dev --extra server
uv run --locked --no-sync uvicorn src.api:app --reload --port 8000
# open http://localhost:8000/
```

**That is not a demo mode.** Most report layers are served from committed JSON
in `static/` and never touch a database, so you get the core public report:
every district's results, economics, bonds, equity, the Houston takeover
analysis, and both maps. Database-backed finance features and the model-backed
question box stay unavailable, and the pages say so instead of breaking.

Worth opening too: `/geomap` (real district boundaries), `/map` (the
similarity "seating chart"), `/docs` (interactive API).

## Three tiers

| Tier | Add | Unlocks |
|---|---|---|
| **1** | nothing | Most public report layers from committed artifacts |
| **2** | a Supabase database | Per-year budgets, peers, anomalies, trends, statewide medians |
| **3** | a DeepSeek or OpenAI key + `NLP_DB_URL` | The plain-English question box at `/query` |

## Architecture in one minute

```text
TEA and other public datasets -> scripts/ + sql/ -> committed static JSON
                                           \-> Supabase Postgres
browser -> FastAPI (src/api.py) -> static portal or read-only DB views
                              \-> NLP engine -> selected LLM -> nlp_reader DB role
Vercel Git integration <- master; GitHub Actions verifies CI and the live revision
Vercel Cron -> authenticated intelligence/outreach routes -> Postgres state
```

The frontend has no build step: FastAPI serves the pages and versioned JSON in
`static/`. Supabase supplies the live finance views and durable operational
state. The model-backed query route is optional and fails closed unless it has
both a provider key and the least-privilege `NLP_DB_URL`. See
[PROJECT_MAP.md](PROJECT_MAP.md) for the visual tour and
[docs/TECH_STACK_AND_AGENT_SKILLS.md](docs/TECH_STACK_AND_AGENT_SKILLS.md) for
the evidence-backed component inventory.

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

Set `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` **and** `NLP_DB_URL`.
When `NLP_PROVIDER` is unset, `src/llm_config.py` prefers DeepSeek when both
provider keys exist. The database URL matters: `/query` hands a visitor's
question to a language model that writes its own SQL, and
limiting the tables it is *told about* does not limit what the connection is
*allowed to run*. Without `NLP_DB_URL`, `/query` refuses to initialize; it does
not fall back to the database owner. See
[docs/AUDIT_2026-07-31.md](docs/AUDIT_2026-07-31.md) C-1 for why that boundary
must fail closed.

## Environment variables

Copy `env_template.txt` to `.env`; never commit the resulting `.env` file.
The minimum configuration depends on the tier:

| Capability | Variables |
|---|---|
| Live finance data | `SUPABASE_DB_URL` |
| Plain-English questions | `NLP_DB_URL` plus `DEEPSEEK_API_KEY` or `OPENAI_API_KEY`; optional `NLP_PROVIDER` |
| Site lock | `SITE_PASSWORD`; optional `SITE_USERNAME` |
| Scheduled routes | `CRON_SECRET` |
| Armed outreach | `RESEND_API_KEY`, `TAG_POSTAL_ADDRESS`, `OUTREACH_TOKEN`; see `docs/OWNER_KEYS.md` before enabling |
| Private operational status | `OPS_TOKEN` |

Optional model, rate-limit, data-year, sender, mailbox, map, and operator-tool
variables are documented in the complete table in
[DEPLOYMENT.md](DEPLOYMENT.md#4-configuration-reference). The commented,
copyable inventory is [env_template.txt](env_template.txt). Host secrets belong
in Vercel/your deploy platform; management credentials such as `SUPABASE_PAT`
and `VERCEL_TOKEN` are for explicit operator scripts, not normal request paths.

## Endpoints

**[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) is the generated
inventory** — every route, every data file and all 617 published fields, read
out of the real files at build time and re-checked by a test. `/docs` is the
live OpenAPI contract. The shape:

**No database needed (53 routes)** — every report layer is a committed JSON
artifact the API serves directly:

| Area | Routes |
|---|---|
| Money | `/economics/texas`, `/spending/texas`, `/tax/texas`, `/trends/texas` and their `/district/{n}/…` forms |
| Results | `/district/{n}/outcomes`, `/performance/texas`, `/district/{n}/performance`, `/district/{n}/campus-performance`, `/campuses/texas`, `/equity/texas`, `/takeover/houston` |
| Obligations | `/bonds/texas`, `/debt/texas` and their per-district forms |
| Context | `/national/texas`, `/erate/texas`, `/forensics`, `/forensics/texas`, `/forensics/quality` |
| Evidence | `/district/{n}/lineage/{metric}`, `/lineage/texas/{metric}`, `/provenance`, `/sources` |
| Maps & discovery | `/map`, `/geomap`, `/district-geo`, `/map-data`, `/fallback-index`, `/mcp`, `/.well-known/mcp.json`, `/feed`, `/sitemap.xml` |

**Database needed (21 routes)** — `/districts`, `/district/{n}/summary`,
`/district/{n}/peers`, `/district/{n}/breakdown`, `/district/{n}/dollar`,
`/district/{n}/turnarounds`, `/district/{n}/insights`,
`/district/{n}/spending-detail`, `/benchmarks`, `/anomalies`, `/stats`,
`/briefing`, `/query`, `/health`, `/api/cron/*`

**Token-gated, listed nowhere in the site** — `/ops/intel`, `/ops/outreach`,
`/ops/review`, `/ops/outcomes` and their data routes. These read named public
officials' behaviour, so they answer **404, not 403**, when the token is wrong
or unset, and they deliberately do not use `SITE_PASSWORD` (which would take
the public portal private to protect a private page).

`{n}` is a **6-digit string** — `057905` is Dallas ISD. Leading zeros are
load-bearing; any pandas read needs `dtype={"district_number": str}`.

## Layout

```
texas-isd-finances/
├── api/index.py            # Vercel entrypoint (no rewrites in vercel.json — see below)
├── src/
│   ├── api.py              # FastAPI: the portal, 78 public routes, the ops surfaces
│   ├── nlp_engine.py       # Plain English → policy-checked SQL; requires NLP_DB_URL
│   ├── answer.py           # model prose → typed blocks the UI draws as components
│   ├── answer_check.py     # checks those figures against the published artifacts
│   ├── lineage.py          # the publication gate behind every VERIFIED badge
│   ├── absences.py         # says what a blank MEANS (not applicable / didn't happen / unmeasured)
│   ├── migrations.py       # bounded startup schema + privacy controls, advisory-locked
│   ├── isd_cron_runtime.py # atomic daily-intelligence persistence
│   ├── outreach_runner.py  # fail-closed queued outreach drain + run ledger
│   ├── intel.py tracking.py outreach_map.py   # recipient-only analytics
│   └── mcp_*.py            # read-only MCP protocol and finance tools
├── static/                 # The site AND its data — committed together on purpose
│   ├── index.html          # The portal (single file, no build step)
│   ├── map.html geomap.html forensics.html opsreview.html …
│   └── *.json              # 20 artifacts, 25.7 MB — economics · spending_detail ·
│                           #   tax_history · trend · outcomes · campus · campus_performance ·
│                           #   equity · bond · debt · forensic · national · erate ·
│                           #   takeover · district_geo · map_data · fallback_index ·
│                           #   forensic_quality · source_fingerprint · isd_briefing
├── scripts/                # One script per data layer, each → one committed JSON
│   ├── prepare_data.py import_to_supabase.py
│   ├── ingest_*.py         # TEA snapshot, TAPR, accountability, STAAR, property, bonds, E-Rate
│   ├── build_*.py          # one per artifact above
│   ├── coverage_simulation.py    # can the data answer what people ask?
│   ├── ai_performance_probe.py   # given data we hold, is the agent right?
│   ├── verify_live.py verify_sources.py verify_artifacts.py
│   └── check_static_js.py  # parses page JS — a 200 response proves nothing
├── sql/                    # finance views, NLP role/usage, cron, outreach and governance schema
├── tests/                  # 1,186 tests. Runs with no credentials at all
└── docs/                   # DATA_DICTIONARY · PLAIN_ENGLISH · USAGE · TUTORIAL ·
                            #   COVERAGE_SIMULATION · WHAT_A_DOLLAR_BUYS ·
                            #   AUDIT_2026-07-31 · MCP · ENGINEERING_LOG
```

The JSON files in `static/` are build artifacts **and** committed source. The
API serves them directly, which is exactly what makes Tier 1 work.
`.vercelignore` must never exclude `static/`.

⚠️ **`.vercelignore` is a silent third environment.** Anything under `src/` that
opens a file outside `src/`, `static/` or `api/` needs a re-include *and* a
test. `src/sources.py` reads `scripts/freshness_vintages.json` at request time;
when `.vercelignore` dropped `scripts/`, the deployed site answered "we do not
know" for freshness and every lineage verdict fell to UNVERIFIED — while the
test suite stayed green, because the repo checkout has the file.

## Rebuilding the data after a TEA release

Order matters — later builders read earlier artifacts.

```bash
# 1. the finance spine
python scripts/prepare_data.py path/to/tea-release.xlsx   # Excel → clean CSV
python scripts/build_provenance_fixture.py                # SHA-anchors the source

# 2. sources that need their own download
python scripts/ingest_tea_snapshot.py --download
python scripts/ingest_tea_property.py --download
python scripts/ingest_tea_accountability.py --download
python scripts/ingest_tapr.py --download        # campus STAAR + staff
python scripts/ingest_bond_elections.py         # Bond Review Board
python scripts/ingest_brb_debt.py
python scripts/ingest_erate.py                  # USAC

# 3. artifacts, in dependency order
python scripts/build_outcomes_data.py           # before build_district_geo
python scripts/build_district_geo.py --counties path/to/tiger-counties
python scripts/build_economics_data.py          # read by forensic + trend
python scripts/build_spending_detail.py
python scripts/build_tax_history.py
python scripts/build_campus_data.py
python scripts/build_campus_performance.py
python scripts/build_equity_data.py
python scripts/build_bond_data.py               # before the crosswalk
python scripts/build_district_crosswalk.py
python scripts/build_debt_data.py
python scripts/build_national_data.py
python scripts/build_erate_data.py
python scripts/build_trend_data.py
python scripts/build_forensic_data.py
python scripts/build_forensic_quality.py
python scripts/build_takeover_data.py
python scripts/build_fallback_index.py --from-live   # LAST — reads the others

# 4. prove it
python scripts/verify_artifacts.py    # rebuilds each and byte-diffs
python scripts/build_data_dictionary.py   # regenerate docs/DATA_DICTIONARY.md
python -m pytest -q
```

After importing to the database: `REFRESH MATERIALIZED VIEW public.v_anomaly_flags;`

⚠️ `build_district_geo.py` needs `--counties` (a TIGER county shapefile)
whenever any district name is shared. Eleven Texas names belong to two
districts each; without the county check the build **refuses** rather than
guessing, which is correct — a naive name join once drew five districts on
another district's land while reporting `unmatched polygons: 0`.

## Developing

```bash
python -m pip install "uv==0.11.33"
uv sync --locked --all-extras --group dev
uv run --locked --no-sync ruff check .
uv run --locked --no-sync pytest
uv run --locked --no-sync python scripts/check_static_js.py
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

## Known limitations

Stated plainly, because a portal about public money should be honest about its
own edges.

- **Every finance figure is an ACTUAL, not a budget.** The latest fiscal year is
  2025; outcomes are 2024; the national comparison is Census FY2024. Nothing
  here can answer a question about this month, next year's budget, or whether a
  district is about to close a school. TEA publishes with a lag and no amount of
  engineering removes it.
- **The measured answerability ceiling is about 84%, not 100%.** The remaining
  gap needs an enrollment projection and a current-year budget the state has not
  released. Publishing either would mean asserting a forecast as a fact, which
  this project declines to do. See
  [docs/COVERAGE_SIMULATION_2026-08-23.md](docs/COVERAGE_SIMULATION_2026-08-23.md) §14.
- **Charters are structurally different, not missing.** A charter levies no
  property tax, holds no bond election, has no attendance boundary and gets no
  Census F-33 row. Those come back as `not_applicable` with a sentence saying
  why — never as a blank or a zero.
- **A masked or unreported value is never rendered as zero.** TEA suppresses
  small student groups to protect identifiable children, and a district that
  reports no food-service line usually runs none. Both are omitted. A zero would
  publish a failing score, or rank every non-reporter as the thriftiest in Texas.
- **Effect sizes are observational.** Within-district first differences remove
  everything about a district that does not change, but not confounders that
  move at the same time. About three quarters of the difference between
  districts is unexplained by anything the state publishes.
- **`/query` can be wrong.** It is a language model writing SQL. Its answers are
  now cross-checked against the published artifacts (`src/answer_check.py`) and
  a weekly job holds it to an accuracy floor, but `unchecked` is deliberately
  not `agrees` — most sentences contain a figure nobody can verify. Prompt
  injection remains a live resource and spend risk, never "harmless".
- **Two published figures can legitimately disagree.** The finance view is
  all-funds *including* construction; the economics artifact is operating plus
  debt. Both are right about different questions, and the site says which basis
  it used rather than quietly picking one.
- **Analytics are recipient-only.** Anonymous visitors are a daily counter with
  no cookie, no IP and no row. Per-person tracking begins only when someone
  arrives with a `?rid=` we minted and mailed — and `/about#privacy` says so.

## When something goes wrong

Start at the top; each step is cheap and rules out a whole class of problem.

| Symptom | First check | Usual cause |
|---|---|---|
| Site returns 404 everywhere, build says READY | `cat vercel.json` | A `rewrites` block. There must be none — it passes the *destination* path to FastAPI. |
| "Database not connected" | `curl -s https://txisd.dev/health` | Supabase free tier pauses after ~7 days idle. Wake it in the dashboard. The 53 DB-free routes keep working throughout. |
| A page looks broken but returns 200 | `python scripts/check_static_js.py` | A JS syntax error. A 200 proves nothing and grepping the served HTML proves less — parse the script. |
| A figure looks wrong | `python scripts/verify_artifacts.py` | An artifact drifted from its source, or a builder was edited and never re-run. |
| A source link is alive but the data looks stale | `python scripts/check_freshness.py` | The publisher shipped a new release. Bump `scripts/freshness_vintages.json` to acknowledge it. |
| The deployed site disagrees with this repo | `python scripts/verify_live.py` | The only check that compares production against the tree. Exits non-zero on drift. |
| A scheduled job seems dead | `curl -s https://txisd.dev/api/cron/runs` | A gap in `cron_runs` is the finding. A job that never fires and a job that writes nothing look identical from outside — this is what distinguishes them. |
| Outreach sends nothing | `curl -s 'https://txisd.dev/api/cron/runs?job=outreach-drain'` | `skipped` / `unarmed` means the three outreach variables are not set. Working as designed. |
| The agent answers with a wrong number | `python scripts/ai_performance_probe.py --n 12` | Ground truth comes from the same endpoint the site serves, so a failure here is the agent, never the data. |
| Something needs a human decision | `/ops/review` (needs `OPS_TOKEN`) | The intelligence pipeline refused to publish a finding on its own. |

`docs/ENGINEERING_LOG.md` is the append-only record of every past incident and
why each fix looks the way it does. If a piece of code seems strange, the reason
is usually in there.

## Security and governance

- `/query` requires **`nlp_reader`** — `USAGE` on `public` plus SELECT on only
  two public views, with no CREATE, base-table, or public-function rights. An
  exact SQLGlot AST/function policy rejects session-affecting SELECTs and
  unreviewed syntax before a read-only, timeout-bounded transaction executes.
  Treat prompt injection as residual resource/spend risk, never as harmless.
- `QUERY_GLOBAL_LIMIT` and `QUERY_DAILY_LIMIT` are counted **in the database**,
  so they hold across every serverless instance rather than per-process. Token
  spend is metered on the same row. **All of it caps calls and tokens, not
  dollars — a provider-side spend limit is still owed.**
- Row-level security on every table holding contact details or named officials'
  behaviour, with `nlp_reader` explicitly revoked: a prompt injection that
  reached the query role must not be able to read who has been written to.
- Private operator routes answer **404, not 403**. A 403 confirms the route
  exists, which is what a token gate is for. Non-ASCII tokens are handled too —
  `secrets.compare_digest` raises on a non-ASCII `str`, and the resulting 500
  once revealed a private route's existence.
- Security headers set by the app, so they survive the deploy target.
- No credentials in the repo. Ever. Host environment variables only.

**Approval and authority.** Outbound email is the only action this system takes
in the outside world, and it is gated three ways: a human with `OUTREACH_TOKEN`
must stage a wave and type the literal word `GO`; the daily cron only drains
what a human queued; and every rail is re-checked at send time rather than at
queue time. `public.outreach_run` records which gate authorized each run — the
gate's **name**, never a token value.

Two surfaces exist so the system can be supervised and judged:

- **`/ops/review`** works the intelligence pipeline's approval queue. It records
  a status and nothing else — it cannot publish, send or edit a briefing — and
  resolving an already-resolved item returns **409, not an overwrite**, so a
  disagreement between two reviewers stays visible.
- **`/ops/outcomes`** records what an email actually produced, entered by a
  person and **never inferred from behaviour**. An open is a mail scanner as
  often as a reader. The report publishes `districts_never_followed_up` beside
  every count, because that is the honest denominator for any rate quoted from
  it.

Full findings and how each was verified:
[docs/AUDIT_2026-07-31.md](docs/AUDIT_2026-07-31.md).

## Deploying

[DEPLOYMENT.md](DEPLOYMENT.md) has the runbook for Render, Docker and Vercel.
Two things that have each cost a production outage:

- **`vercel.json` must contain no `rewrites` block.** Vercel changed
  backend-framework routing so an internal rewrite passes the *destination*
  path to the app — the old rule made FastAPI receive `/api/index` for every
  request and 404 the entire site while the build still reported READY.
- **Production currently deploys from `master` through Vercel's Git
  integration.** `.github/workflows/deploy.yml` holds no Vercel credentials
  and does not deploy; it waits until `/health` reports the expected Git SHA,
  healthy/connected state, and `tracking_schema=ready`, then runs strict live
  checks. A Vercel *redeploy* reuses an old deployment's
  tree and cannot pick up a new commit.

## License

[MIT](LICENSE). Free to use, modify and redistribute. This exists to make
Texas school funding legible to the people paying for it.

Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). This project is
independent — not a TEA product, and it does not rank, recommend or endorse
any district.

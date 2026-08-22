# Technology Stack Forensic and Official Agent Skills Map

> **Audit state:** evidence-backed inventory and adoption plan; no external
> skill has been installed by this document.
>
> **Verified:** 2026-08-22 against `master` at
> `4ca94370b04f183334c7c946cb66586fad4d0bf5`, plus read-only checks of the
> live service and publisher-owned sources linked below.

## Executive finding

Texas ISD Finances is not just a FastAPI application attached to Supabase.
The live system is a Vercel-hosted Python service with a static-data survival
layer, a LangChain SQL agent, DeepSeek as the active model provider, Supabase
Postgres, two Vercel Cron jobs, GitHub Actions monitoring, Resend delivery,
first-party analytics, and a hand-written public MCP server. A larger offline
Python toolchain builds the committed public-data artifacts from state and
federal sources. Docker and Render exist as alternatives, not live production
deployments; OpenAI is a configuration-selected alternate and Mapbox is an
optional upgrade, not the current core path. There is no automatic failover
from DeepSeek to OpenAI after a request failure.

Read-only production checks on 2026-08-22 established that:

- `https://txisd.dev/health` reported healthy, database connected, and
  `deepseek:deepseek-v4-flash` configured.
- `/api/cron/runs` showed the daily `isd-intelligence` job completed that day,
  wrote 372 rows, and had no gap or empty successful runs in its window.
- `/.well-known/mcp.json` advertised the live, read-only `/mcp` endpoint.

Publisher-owned or publisher-hosted Agent Skills material exists for the
parts of this stack where current procedural knowledge matters most: FastAPI,
Pydantic, Supabase/Postgres, Vercel, LangChain, Resend, Mapbox, GitHub
workflows, OpenAI/Codex, Render, and Claude/Anthropic. Google publishes Gmail
skills inside its Workspace CLI repository, but that catalog explicitly is
not an officially supported Google product and does not match this app's IMAP
implementation. The right first move is to document and review these skills,
not install all of them. Several packs contain scripts or mutable operations,
and generic vendor advice must never override this project's database,
privacy, deployment, or outreach invariants.

Agent Skills improve engineering and operating workflows. They are not
application runtime dependencies and none is added to production by this
guide.

## Navigate this forensic

| Need | Section |
|---|---|
| Architecture and active products | [System topology](#system-topology) and [complete stack](#complete-application-and-infrastructure-stack) |
| Optional, development, and source products | [Configured paths](#configured-optional-and-alternate-paths), [toolchain](#development-and-offline-data-toolchain), and [data sources](#external-public-data-and-discovery-sources) |
| Credential/config names | [Configuration surface](#configuration-surface) |
| Which official skills exist | [Availability audit](#official-agent-skills-availability-audit) and [trust check](#reproducibility-and-trust-check) |
| How, where, and why to use them | [Usage map](#how-where-and-why-to-use-the-relevant-skills) |
| What may be installed or operated | [Adoption and authority](#adoption-and-authority-model) |
| Risks and maintenance | [Forensic follow-ups](#forensic-findings-that-need-follow-up), [negative findings](#deliberate-negative-findings), and [maintenance](#maintenance-checklist) |

## Scope and evidence rules

This audit uses four statuses:

| Status | Meaning |
|---|---|
| **Production-active** | The live request, storage, delivery, deployment, or monitoring path uses it, supported by code/config and, where possible, a live read. |
| **Configured/optional** | A real integration or alternate path exists, but it is token-, secret-, feature-flag-, or operator-dependent, or is not the live deployment. |
| **Development-only** | Used to build data, test, lint, analyze, publish, or operate the project; not imported by the Vercel request bundle. |
| **Data-source-only** | An upstream publisher, catalog, feed, or API supplies evidence; it is not application infrastructure. |

Evidence precedence is: executable code and deployment configuration, then a
read-only live check, then current repository documentation, then inference.
When those disagree, this guide records the disagreement instead of blending
the claims. Direct dependencies and services are inventoried; ordinary
transitive packages are not treated as separately selected products.

For skills, **official** means one of:

1. the product publisher owns the repository or ships the skill with the
   library;
2. the publisher's documentation points to it; or
3. for GitHub's `awesome-copilot`, GitHub owns and documents the collection,
   while individual entries remain explicitly community-authored.

A marketplace listing, a `skills.sh` entry, or a repository name that merely
contains a vendor name is not sufficient proof.

## System topology

```mermaid
flowchart TB
    U["Public browser / API / MCP client"] --> V["Vercel: FastAPI + static portal + Cron"]
    V --> P["Supabase Postgres + first-party analytics"]
    V --> L["LangChain SQL agent"]
    L --> D["DeepSeek active / OpenAI alternate"]
    V --> J["Committed JSON survival layer"]
    V --> R["Resend delivery"]
    C["GitHub Actions: CI, monitors, reply/KPI jobs"] --> V
    C --> G["Gmail IMAP replies + Resend status"]
    S["State and federal public sources"] --> B["Offline Python ingestion and builders"]
    B --> J
    B --> P
```

## Complete application and infrastructure stack

### Production-active request, data, and operations path

| Layer | Product or technology | What it does here | Repository evidence | Official skills status |
|---|---|---|---|---|
| Language | Python 3.10+; production target 3.12 | Runs the API, agent, migrations, jobs, and offline builders. | `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml` | No PSF product skill located. |
| API | FastAPI | ASGI application, public JSON API, static pages, auth gates, cron handlers, and OpenAPI schema. | `src/api.py`, `api/index.py` | **Yes:** versioned `fastapi` library skill. |
| Validation | Pydantic 2 | Request/response models and validation. | `src/api.py`, `requirements-vercel.txt` | **Yes:** Pydantic's standalone `pydantic` skill; the FastAPI skill also covers common integration patterns. |
| Database runtime | `asyncpg` | Async connection pool to the Supabase transaction pooler; statement caching is disabled for pooler compatibility. | `src/api.py` (`get_pool`) | No driver skill; use Supabase/Postgres guidance. |
| SQL/DB adapter | SQLAlchemy 2 + `psycopg2-binary` | LangChain SQL access and synchronous import/operator paths. | `src/nlp_engine.py`, `scripts/import_to_supabase.py`, runtime requirements | No publisher Agent Skills pack located. |
| Configuration | `python-dotenv` + environment variables | Local environment loading and deploy-time configuration. | `src/api.py`, `src/nlp_engine.py`, `env_template.txt` | No publisher skill located. |
| Primary database | Supabase hosted Postgres and pooler | Finance views, analytics, outreach state, tracking, cron ledger, RLS, and least-privilege NLP role. | `sql/`, `src/migrations.py`, `src/api.py`, `PROJECT_MAP.md` | **Yes:** `supabase` and `supabase-postgres-best-practices`. |
| Primary hosting | Vercel Python serverless | Runs the ASGI entrypoint behind `txisd.dev`; provides deploys, function execution, CDN behavior, and custom-domain routing. | `api/index.py`, `vercel.json`, `.vercelignore`, `.github/workflows/deploy.yml` | **Yes:** `vercel-optimize`, `vercel-cli-with-tokens`, and `web-design-guidelines`; `deploy-to-vercel` is conditional. |
| Scheduling | Vercel Cron | Daily district-intelligence refresh and daily outreach queue drain. | `vercel.json`, `/api/cron/isd-intelligence`, `/api/cron/outreach-drain` | Covered by Vercel material; repository-specific auth and idempotency rules remain authoritative. |
| Static data tier | Committed JSON and images in `static/` | Serves most report layers without a live database and keeps the portal useful during a DB outage. | `static/*.json`, artifact loaders and routes in `src/api.py` | No vendor skill; project invariants and artifact tests govern it. |
| Frontend | Handwritten HTML, CSS, and ES JavaScript | Portal, reports, first-party tracking, Canvas/SVG visualizations, and fetch-based API calls with no frontend build. | `static/*.html`, `static/design.css`, `static/ask.js`, `static/track.js` | Vercel `web-design-guidelines` is relevant; React/Next.js skills are not. |
| AI framework | LangChain 1.x | Creates the tool-using SQL agent and connects it to read-only database views. | `src/nlp_engine.py`, `requirements-vercel.txt` | **Yes:** `ecosystem-primer`, `langchain-dependencies`, `langchain-fundamentals`, and selectively `langchain-middleware`. |
| SQL toolkit | `langchain-community` | Supplies `SQLDatabase` and `SQLDatabaseToolkit`. | `src/nlp_engine.py` | Same LangChain pack, but this dependency is explicitly sunset and is a migration risk. |
| Provider adapter | `langchain-openai` + OpenAI SDK | Uses `ChatOpenAI` for both OpenAI and DeepSeek's compatible API. | `src/llm_config.py`, `src/nlp_engine.py` | LangChain pack plus OpenAI troubleshooting only when OpenAI is selected. |
| Active LLM | DeepSeek API, `deepseek-v4-flash` | Current `/query` model and optional news extraction provider when enabled. | `src/llm_config.py`, `.github/workflows/llm-balance.yml`; confirmed by live `/health` | No app-relevant publisher Agent Skills pack was located. |
| Email delivery | Resend API | Sends queued superintendent outreach and supplies delivery status for KPI snapshots. | `src/outreach_email.py`, `src/outreach_runner.py`, `scripts/outreach_kpi.py` | **Yes:** `resend`, `email-best-practices`, and optionally `resend-cli`. |
| Source control | GitHub | Canonical public repository and pull-request history. | Git remote and `PROJECT_MAP.md` | **Yes:** GitHub-owned `awesome-copilot` collection; mixed community authorship. |
| CI/monitoring | GitHub Actions | Tests Python 3.10-3.12, parses browser JS, monitors live health/drift/freshness, checks LLM balance, ingests replies, and snapshots outreach KPIs. | `.github/workflows/*.yml` | **Yes:** `github-actions-hardening`, `github-actions-efficiency`, and related workflow skills. |
| Analytics | First-party events and aggregates in Supabase | Counts traffic and recipient journeys without Vercel Analytics; public reply logs expose counts only. | `src/analytics.py`, `src/tracking.py`, `src/intel.py`, `sql/create_analytics.sql`, `sql/create_visitor_tracking.sql` | Supabase skills apply; project privacy rules override generic analytics advice. |
| Agent interface | Hand-written Model Context Protocol 2026-07-28 endpoint | Exposes 11 deterministic, read-only tools over committed artifacts; each result carries data limits. | `src/mcp_protocol.py`, `src/mcp_tools.py`, `docs/MCP.md` | Anthropic `mcp-builder` is useful for review; do not assume SDK handshake behavior matches this stateless implementation. |
| News inputs | TEA newsroom HTML + Google News RSS | Supplies the daily district-intelligence feed. | `scripts/isd_intel.py`, cron path in `src/api.py` | No relevant publisher-owned skill pack located. |

### Configured, optional, and alternate paths

| Product or technology | Status and role | Evidence | Important boundary |
|---|---|---|---|
| OpenAI API, default `gpt-4o-mini` | Configuration-selected alternate when `NLP_PROVIDER=openai`, or the default when no provider is forced and no DeepSeek key exists. | `src/llm_config.py`, `DEPLOYMENT.md` | Not the provider reported live on 2026-08-22; this is selection, not automatic request failover. |
| Mapbox GL JS | Optional enhancement for `/heatmap`, dynamically loaded from Mapbox CDN when a public token is configured. | `static/heatmap.html`, `/mapbox-token`, Mapbox CSP in `src/api.py` | `/geomap` is vendor-free Canvas; Mapbox is not required for the core map. |
| Gmail-compatible IMAP | Credential-dependent inbound reply job using Python's standard library and a Gmail App Password by default. | `scripts/ingest_replies.py`, `.github/workflows/replies.yml` | The workflow exits successfully when secrets are absent; repository inspection cannot prove it is armed. Google's Workspace CLI publishes Gmail skills, but they target the Google API/CLI rather than this IMAP path. |
| Vercel CLI deploy workflow | Alternate production deploy path using Node 20 and Vercel CLI. | `.github/workflows/deploy.yml` | The workflow says it must remain inert while Vercel Git integration is connected, or duplicate deploys race. |
| Docker + Uvicorn | Portable alternate image/runtime. | `Dockerfile`, full requirements | Not the live production host. |
| Render + Uvicorn | Blueprint-based alternate host. | `render.yaml` | Not the live production host and its LLM configuration still describes OpenAI only. Render publishes conditional skills for Blueprints, web services, environment variables, Docker, deployment, debugging, and monitoring. |
| Optional LLM news extraction | Feature-flagged extraction with a hard call budget. | `ISD_LLM_EXTRACT` path in `src/api.py` | Off unless explicitly enabled. |
| Supabase Management API | PAT-authenticated operator path for schema/data synchronization and reply/KPI jobs. | `scripts/sync_outreach_contacts.py`, `scripts/ingest_replies.py`, `scripts/outreach_kpi.py` | Not the normal live request data path; mutable calls require explicit target verification. |
| GitHub Releases API | Optional raw-data archive publishing. | `scripts/archive_raw_data.py` | Upload requires `GITHUB_TOKEN`; local archive creation does not. |

### Development and offline data toolchain

| Purpose | Products and libraries | Evidence |
|---|---|---|
| Package/build resolution | `uv` on Vercel; `pip` in local, CI, Docker, and Render flows | `pyproject.toml`, workflows, `Dockerfile`, `render.yaml` |
| Testing | pytest and HTTPX | `requirements-dev.txt`, `tests/`, `pyproject.toml` |
| Linting | Ruff | `pyproject.toml`, `.github/workflows/ci.yml` |
| Browser-script syntax gate | Node.js `--check` | `scripts/check_static_js.py`, CI workflow |
| Data frames and numeric work | pandas and NumPy | `scripts/prepare_data.py`, multiple `scripts/build_*.py` files |
| Excel ingestion | openpyxl and xlrd | `requirements.txt`, `scripts/build_national_data.py`, TEA import paths |
| Offline visualizations | Matplotlib, Seaborn, and Plotly | `src/visualizations.py`, `requirements.txt` |
| Shapefile processing | pyshp | `scripts/build_district_geo.py`, `scripts/simulate_map_value.py` |
| Social-card rendering | Pillow | `scripts/build_share_cards.py` |
| Network clients | Primarily Python standard-library `urllib` and `imaplib` | ingestion, verification, outreach, and monitoring scripts |

NumPy and Pillow are imported directly but are not declared directly in any
requirements file. They currently arrive transitively (or from an operator's
environment), which makes offline rebuilds less reproducible. There is also no
committed Python lockfile, even though production resolves dependencies at
build time.

## External public-data and discovery sources

These are evidence providers, not runtime frameworks. Their provenance and
freshness rules live in `src/sources.py`, `scripts/freshness_vintages.json`,
`static/sources.html`, and the ingestion/build scripts.

| Publisher/product | Data used |
|---|---|
| Texas Education Agency | Summarized PEIMS actual finance; Snapshot; STAAR district aggregates; A-F accountability; property/tax inputs; excess-local-revenue/recapture; AskTED superintendent directory; newsroom releases |
| Texas Comptroller | Property values and tax-rate inputs used with TEA records |
| Texas Bond Review Board | School bond election record and debt register |
| Texas Open Data / Socrata | Transport for Bond Review Board and AskTED datasets |
| U.S. Census Bureau | F-33 school finance and TIGER/Line school-district boundaries |
| National Center for Education Statistics | NPEFS state finance and CCD LEA directory bridge |
| Universal Service Administrative Company / FCC E-Rate | FRN status and supplemental entity information |
| U.S. Bureau of Labor Statistics | CPI-U |
| Texas Assessment Research Portal / Cambium | Current STAAR bulk-data path; access constraints are documented in project freshness notes |
| Google News RSS | Keyless discovery feed for district news |

No publisher-owned Agent Skills repositories relevant to these ingestion
formats were located. Treat the project's source-specific builders,
provenance tests, and freshness checks as the authoritative procedures.

## Configuration surface

Names are recorded so operators can map integrations without exposing values.

### Protected credentials

- Database and model: `SUPABASE_DB_URL`, `NLP_DB_URL`, `SUPABASE_PAT`,
  `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`.
- Delivery and mailbox: `RESEND_API_KEY`, `IMAP_PASSWORD`.
- Application gates: `CRON_SECRET`, `OPS_TOKEN`, `OUTREACH_TOKEN`,
  `SITE_PASSWORD`.
- Deployment and publishing: `VERCEL_TOKEN`, `VERCEL_ORG_ID`,
  `VERCEL_PROJECT_ID`, `GITHUB_TOKEN`.

### Non-secret or operational configuration

- Model selection: `NLP_PROVIDER`, `NLP_MODEL`, `NLP_BASE_URL`,
  `NLP_TEMPERATURE`.
- API and security: `CORS_ALLOW_ORIGINS`, `MCP_ALLOWED_ORIGINS`,
  `SITE_USERNAME`.
- Query budgets: `QUERY_RATE_LIMIT`, `QUERY_GLOBAL_LIMIT`,
  `QUERY_DAILY_LIMIT`, `QUERY_DEGRADED_LIMIT`, `QUERY_TIMEOUT_SECONDS`.
- Data and intelligence: `DATA_MIN_YEAR`, `DATA_MAX_YEAR`,
  `ISD_PRIORITY_DISTRICTS`, `ISD_MAX_QUERIES`, `ISD_LLM_EXTRACT`,
  `ISD_LLM_MAX_CALLS`.
- Outreach: `RESEND_FROM`, `RESEND_REPLY_TO`, `TAG_BCC`,
  `TAG_POSTAL_ADDRESS`, `IMAP_USER`, `IMAP_HOST`.
- Operator/platform: `SUPABASE_PROJECT_REF`, `VERCEL_PROJECT`,
  `VERCEL_TEAM`, `SITE_URL`, `ARCHIVE_OUT_DIR`, `PORT`, `PYTHON_VERSION`.
- `MAPBOX_TOKEN` is deliberately returned to the browser and must be a
  URL-restricted public `pk.` token, not a secret token.

`SUPABASE_URL` and `SUPABASE_ANON_KEY` remain in `env_template.txt` but have no
code references. They should be identified as legacy/template-only or removed
in a focused cleanup.

## Official Agent Skills availability audit

### Summary matrix

| Stack owner | Official source | Relevant skills | Adoption decision |
|---|---|---|---|
| FastAPI | [`fastapi/fastapi` library skill at 0.141.1](https://github.com/fastapi/fastapi/tree/0.141.1/fastapi/.agents/skills/fastapi) | `fastapi` | **Recommended for matching API work, version-matched.** High relevance to `src/api.py`; select the upstream tag matching the resolved FastAPI release. |
| Pydantic | [`pydantic/skills`](https://github.com/pydantic/skills) | `pydantic` | **Optional.** Use for non-trivial model, validation, settings, and serialization work; basic API integration is already covered by the FastAPI skill. |
| Supabase | [`supabase/agent-skills`](https://github.com/supabase/agent-skills) and [Supabase skill docs](https://supabase.com/docs/guides/ai-tools/ai-skills) | `supabase`, `supabase-postgres-best-practices` | **Recommended for matching DB work.** Highest-value pair for pooling, migrations, RLS, grants, and query review. |
| Vercel | [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) | `vercel-optimize`, `vercel-cli-with-tokens`, `web-design-guidelines`; conditional `deploy-to-vercel` | **Candidate for matching Vercel work.** Optimize live functions/caching and review the native portal; use deployment material only for an explicitly authorized deploy path and exclude React guidance. |
| LangChain | [`langchain-ai/langchain-skills`](https://github.com/langchain-ai/langchain-skills) | `ecosystem-primer`, `langchain-dependencies`, `langchain-fundamentals`; conditional `langchain-middleware`; later `eval-engineering` | **Candidate with extra review.** The pack calls itself early development; pin and review before use. |
| Resend | [`resend/resend-skills`](https://github.com/resend/resend-skills) | `resend`, `email-best-practices`, optional `resend-cli` | **Recommended for matching email review.** Do not replace durable opt-out and aggregate-log rules with generic examples. |
| Mapbox | [`mapbox/mapbox-agent-skills`](https://github.com/mapbox/mapbox-agent-skills) | `mapbox-token-security`, `mapbox-web-integration-patterns`, `mapbox-web-performance-patterns`, `mapbox-data-visualization-patterns`, `mapbox-style-quality`; optional `mapbox-mcp-devkit-patterns` | **Feature-specific only.** Load for `/heatmap`, not for the core Canvas map. |
| GitHub | [`github/awesome-copilot`](https://github.com/github/awesome-copilot) and its [skills catalog](https://github.com/github/awesome-copilot/blob/main/docs/README.skills.md) | `github-actions-hardening`, `github-actions-efficiency`, `create-github-action-workflow-specification`, `secret-scanning`, `codeql` | **Use after content review.** GitHub owns the collection, but the repository describes it as community-created. |
| OpenAI / Codex | Current [`openai/plugins`](https://github.com/openai/plugins) catalog and [Codex skills/plugins docs](https://developers.openai.com/codex/skills-and-plugins) | `openai-api-troubleshooting`, `openai-platform-api-key`; GitHub workflows `github`, `gh-fix-ci`, `gh-address-comments`; optional `security-diff-scan` | **Use on matching work through the supported plugin mechanism.** The older `openai/skills` catalog is deprecated; OpenAI Developers plugin content is proprietary, so do not copy or vendor it. |
| Render | [`render-oss/skills`](https://github.com/render-oss/skills) | `render-blueprints`, `render-web-services`, `render-env-vars`, `render-docker`, `render-deploy`, `render-debug`, `render-monitor` | **Conditional.** Use only if `render.yaml` becomes an active deploy target. |
| Google Workspace CLI | [`googleworkspace/cli`](https://github.com/googleworkspace/cli) | `gws-gmail`, `gws-gmail-read`, `gws-gmail-watch`, `gws-gmail-triage` | **Do not adopt for the current path.** The catalog targets the Google API/CLI, not `imaplib`, and the repository says the CLI is not an officially supported Google product. |
| Anthropic / Claude | [`anthropics/skills`](https://github.com/anthropics/skills) | `mcp-builder`, `skill-creator` | **Development-only.** Useful for the custom MCP surface and the existing `.claude/skills`, not an application runtime dependency. |

### Reproducibility and trust check

The following revisions were inspected during this audit. They are review
evidence, not automatic dependency pins. Before adopting a skill, re-check the
specific files and use a project-approved commit or release.

| Source | Reviewed revision | License/maturity observation |
|---|---|---|
| `fastapi/fastapi` | tag [`0.141.1`](https://github.com/fastapi/fastapi/tree/0.141.1/fastapi/.agents/skills/fastapi), `95f8322` | MIT. This was the locally resolved release; the unpinned production build still needs its own version check. |
| `supabase/agent-skills` | [`8331f91`](https://github.com/supabase/agent-skills/commit/8331f910845103c08d51f6ca1d86ebb7d1f745e3) | MIT; publisher docs also point to the repository. |
| `pydantic/skills` | [`e5f7cb1`](https://github.com/pydantic/skills/commit/e5f7cb13d01561fe3735040ed37596abd9b83976) | MIT. |
| `vercel-labs/agent-skills` | [`dd089a8`](https://github.com/vercel-labs/agent-skills/commit/dd089a8c752c966dee8bf0f27cb625ba193ffd9e) | README says MIT, but no top-level `LICENSE` was present at the inspected revision; link/install only until clarified. |
| `langchain-ai/langchain-skills` | [`7f00812`](https://github.com/langchain-ai/langchain-skills/commit/7f00812b2b8b3022f766a223db579dd381a23813) | Early-development warning; no top-level `LICENSE` was present at the inspected revision. |
| `resend/resend-skills` | [`2a69b9f`](https://github.com/resend/resend-skills/commit/2a69b9f39a16c043cbfad45fbfa3c141bd27b050) | MIT. |
| `mapbox/mapbox-agent-skills` | [`304d4eb`](https://github.com/mapbox/mapbox-agent-skills/commit/304d4eb7b0c61d999ce1ad690fe368680e2e5993) | MIT (`LICENSE.md`). |
| `github/awesome-copilot` | [`83561bd`](https://github.com/github/awesome-copilot/commit/83561bd7d8a46fcda0581aedabdf8eac7cb196b6) | MIT at repository level; content is community/third-party-sourced. |
| `openai/plugins` | [`11c74d6`](https://github.com/openai/plugins/commit/11c74d6ba24d3a6d48f54a194cd00ef3beea18f9) | No repository-wide license; OpenAI Developers declares `Proprietary` and the GitHub plugin declares MIT. Use installed plugins under their terms rather than copying them here. |
| `render-oss/skills` | [`3f2aa30`](https://github.com/render-oss/skills/commit/3f2aa30eaadc1c2cc6bb402f8eee93f7db844218) | MIT. |
| `googleworkspace/cli` | [`a3768d0`](https://github.com/googleworkspace/cli/commit/a3768d0e82ad83cca2da97724e46bea4ff0e6dbd) | Apache-2.0; project README carries the unsupported-product caveat. |
| `anthropics/skills` | [`3b3fad9`](https://github.com/anthropics/skills/commit/3b3fad96af16a10759d930941b4520ba0c40edae) | The listed `mcp-builder` and `skill-creator` skills are Apache-2.0; other bundled document skills use separate terms. |

### How, where, and why to use the relevant skills

#### FastAPI: `fastapi`

- **How:** use the skill from the upstream tag matching the project's resolved
  FastAPI release. Do not copy `master` guidance into a deployment that may
  resolve an older version.
- **Where:** `src/api.py`, `src/site_gate.py`, `api/index.py`, Pydantic models,
  middleware, streaming/query responses, and `tests/test_api.py`.
- **Why:** it captures current FastAPI routing, response-model, dependency,
  Pydantic, streaming, and frontend-serving patterns. It is particularly useful
  because this application has a large single API module and hand-built static
  routes.
- **Project override:** preserve the Vercel ASGI entrypoint, no-rewrite rule,
  custom `/docs`, explicit static-file allowlist, and existing security headers.

#### Pydantic: `pydantic`

- **How:** use the standalone publisher skill only for model-heavy work; for
  ordinary FastAPI request/response models, load the version-matched FastAPI
  skill first and avoid duplicating guidance.
- **Where:** Pydantic models in `src/api.py`, validation boundaries, serialized
  API shapes, and tests that pin those contracts.
- **Why:** it covers Pydantic 2 validation, serialization, model design, and
  migration concerns without treating framework defaults as universal.
- **Project override:** API response compatibility and six-digit district IDs
  are stronger constraints than a generic model refactor.

#### Supabase: `supabase` and `supabase-postgres-best-practices`

- **How:** use an already-supported plugin/personal skill or inspect the named
  skill from a pinned upstream checkout outside this repository. Load the
  Postgres skill separately only when the task is schema or performance work.
  Read the current Supabase changelog and docs before applying changes. A
  Supabase MCP connection is a separate capability and should start read-only.
- **Where:** `sql/`, `src/migrations.py`, `src/api.py` pool setup, analytics and
  outreach schemas, `scripts/import_to_supabase.py`, and PAT-based operator
  scripts.
- **Why:** this is the most consequential trust boundary in the app: RLS,
  grants, least-privilege `nlp_reader`, serverless pooling, indexes, migrations,
  and performance all live here.
- **Project override:** confirm the exact project before any mutable action;
  use the transaction pooler on Vercel, keep asyncpg
  `statement_cache_size=0`, and never give model-authored SQL owner rights.

#### Vercel: optimization, CLI-token, design, and deploy skills

- **How:** load `vercel-optimize` from a supported plugin/personal skill or a
  pinned, inspected checkout; load `web-design-guidelines` only for a UI
  review. Use live metrics and a preview/branch first. Use
  `vercel-cli-with-tokens` only for an explicitly
  authorized operator path; use `deploy-to-vercel` only if that path is chosen
  over the currently connected Git integration. Never let a skill deploy
  merely because it can.
- **Where:** `vercel.json`, `.vercelignore`, `api/index.py`, cache middleware,
  function/cron behavior, and `static/` UI files.
- **Why:** `vercel-optimize` is evidence-first and can find cost, caching,
  reliability, function-duration, and build-minute problems. The design skill
  fits the native HTML/CSS portal's accessibility and interaction surface.
- **Project override:** target the correct team/project, keep `vercel.json`
  free of rewrites, do not arm both Git integration and the CLI deployment
  workflow, and verify the live tree after deployment.
- **Do not use:** `react-best-practices`; this repository has no React,
  Next.js, or frontend package manifest.

#### LangChain: dependency, fundamentals, middleware, and evaluation skills

- **How:** from a pinned, inspected upstream checkout, start with
  `ecosystem-primer`, then load `langchain-dependencies`; add
  `langchain-fundamentals` only for agent changes. Keep the revision pinned
  because the repository labels itself early development.
- **Where:** `src/nlp_engine.py`, `src/llm_config.py`, provider tests, SQL-tool
  prompt rules, and the planned migration away from `langchain-community`.
- **Why:** it covers the current `create_agent` API, tools, middleware, and
  dependency compatibility—the precise areas most likely to drift in this
  application.
- **Later:** `eval-engineering` could turn known-answer question regressions
  into a stronger agent evaluation suite, but it adds Harbor/Docker workflow
  overhead and is not a first install.
- **Project override:** preserve SELECT-only enforcement, two-view exposure,
  aggregate-count rules, global budget controls, and deterministic tests.

#### Resend: API and email best-practice skills

- **How:** from a pinned, inspected checkout or supported personal skill, load
  only `resend` and `email-best-practices`; add `resend-cli` only for explicit
  operator work.
- **Where:** `src/outreach_email.py`, `src/outreach_runner.py`,
  `scripts/send_outreach.py`, `scripts/outreach_kpi.py`, and the outreach
  workflows.
- **Why:** it adds current API, deliverability, authentication, webhook,
  accessibility, compliance, and retry guidance around a high-consequence
  outbound system.
- **Project override:** opt-outs must be durable before success is reported,
  send-time suppression must remain fail-closed, public logs must never contain
  addresses or correspondence, and retries must never convert uncertain sends
  into duplicates.
- **Do not use now:** `react-email` (templates are Python-rendered HTML) or
  `agent-email-inbox` (the current inbound path is Gmail IMAP). Either would be
  an architecture change, not a documentation install.

#### Mapbox: token security, web integration, performance, and visualization

- **How:** load one task-specific skill from a pinned, inspected
  `mapbox/mapbox-agent-skills` checkout; use `mapbox-mcp-devkit-patterns` only
  if the team separately approves and tests the MCP connection.
- **Where:** `static/heatmap.html`, the Mapbox-specific CSP in `src/api.py`,
  and `/mapbox-token`.
- **Why:** `/heatmap` is a choropleth with dynamic CDN loading, GeoJSON,
  data-driven styling, public-token restrictions, and accessibility/performance
  concerns directly covered by `mapbox-token-security`, integration,
  performance, visualization, and style-quality guidance.
- **Project override:** Mapbox stays optional; `/geomap` must continue to work
  without it, and only a URL-restricted public token may reach the browser.

#### GitHub: Actions hardening and repository workflows

- **How:** inspect the exact selected skill and bundled scripts at a pinned
  revision, then load it through a supported personal/plugin mechanism. The
  collection is community-created even though it lives in the GitHub
  organization; do not fetch a mutable default branch into this repository.
- **Where:** `.github/workflows/`, branch/PR operations, release archival,
  security review, and future repeat forensic passes.
- **Why:** five scheduled or deployment-related workflows depend on secret
  boundaries, shell interpolation, token permissions, and fail-open/fail-green
  behavior that ordinary Python linting cannot analyze.
- **Project override:** workflow writes, dispatches, secret changes, merges,
  releases, and deploys require the user's authority; read-only review does not
  grant operational permission.

#### OpenAI/Codex: current plugins, troubleshooting, and security

- **How:** use the current OpenAI plugin catalog and documentation. The
  `openai/skills` repository now points users to `openai/plugins` and is not
  the current adoption source. Use the supported plugin mechanism; the
  OpenAI Developers plugin is proprietary and must not be copied into this
  repository.
- **Where:** OpenAI alternate-provider behavior in `src/llm_config.py`,
  provider failure handling, credential setup outside the repository, and security review of
  changes to model-authored SQL or MCP surfaces.
- **Why:** `openai-api-troubleshooting` distinguishes network, credential,
  quota, rate-limit, and model/project access failures;
  `openai-platform-api-key` is the credential gate that keeps plaintext keys
  out of chat, output, and git. `security-diff-scan` is appropriate after a
  sensitive change.
- **Do not use:** `agents-sdk` as an automatic rewrite. The application chose
  LangChain and does not use the OpenAI Agents SDK.

#### Render: deployment and operations skills, only if reactivated

- **How:** select the narrow skill needed from `render-oss/skills`; start with
  `render-blueprints` for `render.yaml`, then add deploy, environment, debug,
  monitor, web-service, or Docker guidance only for the task at hand.
- **Where:** `render.yaml`, `Dockerfile`, runtime requirements, and the Render
  environment/provider settings.
- **Why:** the checked-in alternate target can drift even while Vercel remains
  healthy; official deployment and debugging procedures reduce guesswork if
  Render is intentionally reactivated.
- **Project override:** Render is not production evidence. Reconcile the stale
  OpenAI-only configuration and verify a separate target before any deploy.

#### Google Workspace CLI Gmail skills: documented, not adopted

- **How:** do not install these for maintenance of the existing reply-ingest
  job. Re-evaluate `gws-gmail*` only if the application deliberately migrates
  from App-Password IMAP to the Gmail API/Google Workspace CLI.
- **Where:** a future replacement for `scripts/ingest_replies.py` and
  `.github/workflows/replies.yml`, not those files as currently designed.
- **Why:** the official-source match is real but the architecture match is not;
  the catalog's own unsupported-product caveat also makes it a pinned,
  conditional input rather than operational authority.

#### Anthropic/Claude: `mcp-builder` and `skill-creator`

- **How:** use only for explicit MCP or repo-skill authoring work and review
  the referenced assets/scripts first.
- **Where:** `src/mcp_protocol.py`, `src/mcp_tools.py`, `docs/MCP.md`, and the
  existing `.claude/skills/ariba` and `.claude/skills/outreach` workflows.
- **Why:** the repository already uses Claude-style skills and maintains a
  deliberately unusual stateless MCP transport, so current protocol and skill
  packaging guidance is useful.
- **Project override:** do not add an MCP client config until actual Codex and
  Claude round trips prove compatibility; the repository currently contains
  contradictory MRTR documentation and deliberately rejects legacy
  `initialize`.

## Products without an applicable official skill found

As of the verified date, the audit did not locate a publisher-owned,
application-relevant Agent Skills pack for the following direct stack areas:

- DeepSeek API integration.
- Python/PSF, Uvicorn, python-dotenv, SQLAlchemy, asyncpg, psycopg2, pytest,
  HTTPX, NumPy, pandas, openpyxl, xlrd,
  Matplotlib, Seaborn, Plotly, pyshp, Pillow, and Ruff.
- Generic Dockerfile/container authoring. Docker-owned skills exist for Docker
  Agent and Docker Sandboxes, but those do not govern this ordinary fallback
  image. Render's skill applies only to the conditional Render target.
- Gmail IMAP as used here. Google Workspace CLI publishes Gmail API/CLI skills,
  but they are not a procedure for this server-side read-only IMAP job.
- PostgreSQL as a PGDG-published skill. Use Supabase's first-party Postgres
  best-practices skill for this hosted database, plus canonical PostgreSQL
  documentation.
- Socrata/Tyler, TEA, Texas Comptroller, Texas Bond Review Board, Census,
  NCES, USAC/FCC, BLS, Cambium, or Google News RSS ingestion.

“Not found” is time-bound, not proof that a repository can never appear.
Re-run publisher-org and publisher-doc searches before changing this matrix.

## Adoption and authority model

| Tier | Allowed use | Examples for this repository |
|---|---|---|
| **0 — Document** | Record sources, relevance, and guardrails; install nothing. | **This audit.** |
| **1 — Observe** | Read code, docs, logs, metrics, schemas, RLS, deployment state, and security posture. | FastAPI review, Supabase advisors, Vercel metrics, Actions hardening review. |
| **2 — Develop** | Make branch-scoped changes, test locally, use preview/test resources, and open a PR. | Schema migration in a test branch, `/heatmap` fix, LangChain dependency migration. |
| **3 — Operate** | Mutate production or external systems only with explicit authority and a verified target/dry run. | Merge/deploy, production SQL, secret changes, workflow dispatch, Resend send, release upload. |

Skills provide instructions—not credentials, authorization, or proof.
External vendor skills are not committed to this repository. Before loading
one through a supported plugin, personal-skill location, or pinned checkout:

1. verify publisher ownership and the exact repository;
2. inspect `SKILL.md`, every referenced script, network behavior, and license;
3. pin a commit or reviewed release instead of tracking a mutable default
   branch;
4. load only the named skill needed for the task;
5. keep skills out of the Vercel runtime bundle;
6. make the existing project invariants take precedence;
7. test in a fresh agent session; and
8. update deliberately—never auto-update operational skills.

## Forensic findings that need follow-up

| Priority | Finding | Evidence and consequence | Recommended next action |
|---|---|---|---|
| High | `langchain-community` is sunset but supplies the live SQL toolkit. | `src/nlp_engine.py` says it directly; dependency remains in both runtime manifests. | Use pinned LangChain guidance to design and regression-test a supported replacement before the package disappears or breaks. |
| High | Credential-dependent Actions jobs can be green while inert. | `replies.yml` and `outreach-kpi.yml` exit 0 when required secrets are absent. | Add an explicit operational readiness signal or scheduled assertion without exposing secret values. |
| High | The outreach drain is not covered by the daily cron monitor. | `monitor.yml` calls `/api/cron/runs` without `job=outreach-drain`; the endpoint defaults to `isd-intelligence`. An unarmed or stalled outreach drain can remain invisible. | Monitor each Vercel Cron job explicitly and keep secret readiness separate from public run-health output. |
| High | Offline rebuilds depend on undeclared direct imports and no lockfile. | NumPy and Pillow are imported directly but not declared; only requirements ranges are committed. | Declare build dependencies directly and add a reviewed lock/reproducible build policy. |
| Medium | Primary-provider documentation still has drift. | Live and code prefer DeepSeek. This PR corrects README setup, but Project Map and Render material still present OpenAI as primary. | Reconcile the remaining documents from `src/llm_config.py` and live `/health`. |
| Medium | Deployment dependencies and Actions are mutable. | The conditional CLI workflow installs `vercel@latest`; workflows use mutable major action tags. If the alternate deploy path is armed later, tool behavior can change without a repository diff. | Pin a reviewed Vercel CLI version and action commit SHAs, then use a deliberate updater such as Dependabot. |
| Medium | MCP documentation contradicts the implementation. | An early `docs/MCP.md` section says MRTR/input-required is absent; later docs and `src/mcp_tools.py` implement it. | Correct the document and perform actual client round-trip tests before adding repo MCP client config. |
| Medium | Public source vintage label drift remains. | `static/sources.html` labels TIGER boundaries 2024 while the builder uses TIGER2025. | Fix the rendered source label and preserve the existing provenance tests. |
| Low | Unused Supabase template variables imply an SDK path that does not exist. | `SUPABASE_URL` and `SUPABASE_ANON_KEY` have no code references. | Mark them legacy or remove them in a focused config cleanup. |
| Informational | Mapbox, Docker, and Render are easy to overstate. | Code proves Mapbox is optional and Vercel excludes Docker/Render files. | Keep status labels in all future architecture material. |

## Deliberate negative findings

- There is no React, Next.js, Vue, Svelte, Angular, Leaflet, D3, frontend
  package manifest, or browser bundler in the repository.
- Vercel Web Analytics is not used; analytics are first-party and stored in
  Supabase.
- Railway is mentioned in prose but has no repository configuration.
- The public MCP tools do not expose `/query`; they are deterministic reads
  over committed artifacts and do not spend model tokens.
- Render and Docker configuration does not prove additional live deployments.
- A successful credential-dependent workflow does not prove its secrets exist,
  because several jobs deliberately skip with exit code 0.

## Maintenance checklist

Update this guide when any of these changes:

- `pyproject.toml`, requirements, `vercel.json`, `render.yaml`, `Dockerfile`,
  `.vercelignore`, or a GitHub workflow;
- an external hostname, API, environment-variable name, source publisher, or
  live provider;
- a new library or service is imported directly;
- a skill is installed, removed, updated, or granted an MCP connection;
- production moves away from Vercel Git integration, Supabase, DeepSeek, or
  the current cron topology.

For a repeat audit, compare code/config first, call `/health`,
`/api/cron/runs`, and `/.well-known/mcp.json` read-only, then re-check every
official source above. Never infer that a configured integration is active
merely because an environment variable name or workflow exists.

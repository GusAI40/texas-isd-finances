# Services, libraries, tools, protocols, and sources

This is an evidence-based inventory, not a claim that every configured integration is armed. The historical stack record is [docs/TECH_STACK_AND_AGENT_SKILLS.md](docs/TECH_STACK_AND_AGENT_SKILLS.md); source authority is [src/sources.py](src/sources.py).

## Active production path verified 2026-10-07

| Item | Role | Evidence |
|---|---|---|
| Vercel | FastAPI/static hosting and scheduled routes | `vercel.json`, `api/index.py`; live health at revision `73df1896ed0818020ec1c15c06f5ee823db7ec0f`. |
| Supabase Postgres | Finance registry and read-only views | Live health/read-only catalog; pool setup in `src/api.py`, schema in `sql/create_tables.sql`. |
| DeepSeek | Configured NLP provider through OpenAI-compatible client | live health; `src/llm_config.py`. One checked NLP answer is not an accuracy certification. |
| GitHub | Source control verified live | Repository and source references. GitHub Actions is a separately configured automation path below. |
| MCP 2026-07-28 | Stateless public protocol | `src/mcp_protocol.py`, `src/mcp_tools.py`, [docs/MCP.md](docs/MCP.md). |
| First-party analytics | Aggregate anonymous visits plus recipient-only journey data in private ops surfaces | `src/analytics.py`, `src/tracking.py`, `src/intel.py`, `src/api.py`. Schema readiness was checked; end-to-end event writing was not tested in this audit. |

The 11 public MCP artifact tools are `find_district`, `district_money`, `district_lineage`, `district_forensics`, `district_trends`, `district_bonds`, `district_debt`, `district_campuses`, `district_national`, `texas_overview`, and `compare_districts`. They differ from the internal NLP SQL tools `sql_db_list_tables`, `sql_db_schema`, `sql_db_query`, and `sql_db_query_checker` in `src/nlp_engine.py`; `/query` is not exposed through MCP.

## Configured, optional, or development-only

| Item | Status and boundary | Evidence |
|---|---|---|
| OpenAI | Selected alternate; no automatic DeepSeek failover | `src/llm_config.py`, `pyproject.toml`. |
| Resend | Coded delivery; outreach was unarmed during audit | `src/outreach_email.py`, `scripts/send_outreach.py`. |
| Gmail IMAP | Credential-dependent read-only reply ingest; readiness unverified | `scripts/ingest_replies.py`, `imaplib`. |
| Mapbox GL JS | Optional heatmap, dynamically loaded from Mapbox CDN | `static/heatmap.html`; no Google Fonts/framework CDN found. |
| Docker, Render, Uvicorn | Alternate server/development path, not verified production hosting | `Dockerfile`, `render.yaml`, `pyproject.toml`. |
| Operator/archive paths | Supabase Management API and GitHub release archive | Scripts/workflow configuration; not public runtime requirements. |
| Runtime libraries | FastAPI, Pydantic, SQLAlchemy, asyncpg, psycopg2-binary, LangChain, langchain-openai, OpenAI SDK, SQLGlot, python-dotenv | `pyproject.toml`, `uv.lock`. |
| Offline libraries | pandas, numpy, openpyxl, xlrd, matplotlib, seaborn, plotly, pyshp, Pillow | `pyproject.toml` `offline` extra. |
| Dev tools | uv, pytest, httpx, Ruff, Node.js, Git, GitHub CLI | `pyproject.toml`, CI/scripts. |
| GitHub Actions | Configured CI/automation workflows; observed states require per-workflow review | `.github/workflows/{ci,deploy,monitor,answer-quality,llm-balance,replies,outreach-kpi}.yml`. |

## Public data and discovery sources

| Publisher/product | Registered IDs |
|---|---|
| Texas Education Agency (PEIMS, snapshots, STAAR, property, recapture, accountability) | `tea_peims`, `tea_snapshot`, `tea_staar_district`, `tea_property`, `tea_recapture`, `tea_accountability` |
| Texas Comptroller (co-source for property records) | `tea_property` |
| Texas Bond Review Board | `bond_elections`, `brb_debt_outstanding` |
| Texas Open Data/Socrata | Hosting transport for `bond_elections`; not its publisher |
| U.S. Census (F-33 and TIGER) | `census_f33`, `census_tiger` |
| NCES (NPEFS and CCD directory) | `nces_npefs`, `ccd_lea_directory` |
| USAC/Socrata (E-Rate and entities) | `usac_erate`, `usac_entities` |
| U.S. Bureau of Labor Statistics | `bls_cpi` |

Supporting code also identifies TEA AskTED/TAPR, Google News RSS, and Socrata as discovery/ingest mechanisms. The current source register describes a public Cambium path, while freshness/engineering notes document modern-path access constraints; this is a documented conflict that requires review, not a claim of unrestricted access.

All 15 registered checks returned HTTP 200 with publisher-host/content proof on 2026-10-07. That proves this bounded access check, not that every latest release has been ingested; see [docs/AUDIT_2026-10-07.md](docs/AUDIT_2026-10-07.md).

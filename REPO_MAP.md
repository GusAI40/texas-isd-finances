# 🏙️ Repository Blueprint — The City Map

**Verified against:** the actual code, git history, live production, and
connected services on 2026-07-23 (branch `master` @ merge of PR #1). Every
component below carries a repository path and a status. For the friendlier
one-page version, see [PROJECT_MAP.md](PROJECT_MAP.md); for deep technical
detail, see [ARCHITECTURE.md](ARCHITECTURE.md).

**Status legend:** ✅ working & verified · 🟡 partially implemented ·
🔵 documented/planned · 🔴 broken/missing · ⚪ unclear/unverified ·
🗑️ potentially obsolete

---

## 1. Executive Repo Map

The STATE is the whole business; each CITY is a major capability.

```mermaid
graph TB
    subgraph STATE["STATE: Texas ISD Transparency System"]
        C1["CITY: Public Dashboard<br/>static/index.html<br/>✅ live"]
        C2["CITY: JSON API<br/>src/api.py<br/>✅ live"]
        C3["CITY: AI Question Desk<br/>src/nlp_engine.py<br/>✅ live"]
        C4["CITY: Data Vault<br/>Supabase Postgres<br/>✅ 20,587 records"]
        C5["CITY: Data Factory<br/>scripts/ + sql/<br/>✅ run per TEA release"]
        C6["CITY: Inspections<br/>tests/ + .github/workflows/ci.yml<br/>✅ 29 tests"]
        C7["CITY: Town Records<br/>docs/ + *.md<br/>✅ current"]
        C8["CITY: Revenue District<br/>(planned monetization)<br/>🔵 documented only"]
    end
    C1 --> C2 --> C4
    C2 --> C3 --> C4
    C5 --> C4
    C6 -.-> C2
    C7 -.-> C1
    C8 -.->|future| C1
```

## 2. Detailed System Architecture

```mermaid
graph LR
    subgraph VISITORS["RESIDENTS: the public"]
        ADMIN["School administrators<br/>journalists · parents"]
    end
    subgraph VERCEL["HOUSE: Vercel serverless (production)"]
        ENTRY["ROOM: api/index.py<br/>ASGI entrypoint"]
        subgraph API["HOUSE: FastAPI · src/api.py"]
            UI["ROOM: GET /<br/>serves static/index.html"]
            R1["ROOM: /districts · /district/:id/summary"]
            R2["ROOM: /district/:id/peers · /benchmarks"]
            R3["ROOM: /district/:id/breakdown"]
            R4["ROOM: /anomalies"]
            R5["ROOM: /query (rate-limited 10/min/IP)"]
            R6["ROOM: /health · /stats · /docs"]
        end
        NLP["RESIDENT: NLP agent<br/>src/nlp_engine.py<br/>LangChain create_agent + gpt-4o-mini"]
    end
    subgraph SUPA["HOUSE: Supabase Postgres us-east-1"]
        V1["ROOM: v_finance_summary (view)"]
        V2["ROOM: v_anomaly_flags (materialized view)"]
        V3["ROOM: v_spending_breakdown (view)"]
        T["ROOM: texas_school_finance<br/>140 columns · RLS enabled · PK(district,year)"]
    end
    ADMIN -->|HTTPS| ENTRY --> UI
    R1 & R2 & R4 --> V1 & V2
    R3 --> V3
    R5 --> NLP -->|SELECT only via pooler :6543| V1
    V1 & V2 & V3 --- T
```

## 3. Primary Customer Journey

VEHICLE = one administrator's visit. DESTINATION = a board-ready answer.

```mermaid
graph LR
    A["Arrives at<br/>texas-isd-finances.vercel.app"] --> B["First visit?<br/>60-second guided tour<br/>(TOUR array, static/index.html)"]
    B --> C["STREET: picks district<br/>GET /districts?search="]
    C --> D["Executive summary paragraph<br/>+ 4 KPI tiles<br/>(renderExec, renderKPIs)"]
    D --> E["Trends vs state median<br/>GET /benchmarks + /summary"]
    D --> F["Peer ranking<br/>GET /district/:id/peers"]
    D --> G["Money breakdown<br/>GET /district/:id/breakdown"]
    D --> H["Anomaly cards w/ numbers<br/>GET /anomalies?district_number="]
    E & F & G --> I["DESTINATION:<br/>Print PDF · PNG charts · CSVs<br/>for the board packet"]
    H --> J["DESTINATION:<br/>informed answer to<br/>'why were we flagged?'"]
    I & J --> K["REVENUE OUTCOME 🔵:<br/>trust + audience —<br/>the asset any paid tier<br/>would be built on"]
```

## 4. Agent-and-Tool Workflow

The one AI RESIDENT and its TOOLBOX (full inventory: [AGENTS.md](AGENTS.md)).

```mermaid
graph TB
    Q["VEHICLE: plain-English question<br/>POST /query {question}"] --> RL{"Rate limiter<br/>10/min/IP<br/>(_rate_limited, src/api.py)"}
    RL -->|429| STOP["Friendly 'wait a minute'"]
    RL -->|ok| ENG["RESIDENT: TexasFinanceNLPEngine<br/>src/nlp_engine.py<br/>langchain.agents.create_agent"]
    ENG --> SYS["Guardrail: SYSTEM_PROMPT<br/>SELECT-only · LIMIT 100 ·<br/>schema of the 2 views"]
    ENG --> TB["TOOLBOX: SQLDatabaseToolkit<br/>list tables · show schema ·<br/>check SQL · run SQL"]
    TB --> DB["Supabase — sees ONLY<br/>v_finance_summary + v_anomaly_flags<br/>(include_tables allowlist)"]
    DB --> ANS["DESTINATION: cited answer<br/>rendered in the ask box"]
    ANS --> REV["REVENUE OUTCOME 🔵: differentiator<br/>feature for any future paid API tier;<br/>today a cost center (~$0.001/question)"]
```

## 5. Data Lifecycle

```mermaid
graph LR
    TEA["SOURCE: TEA release<br/>tea.texas.gov /media/423296<br/>Excel, sheet DATAMART"] --> P1["scripts/prepare_data.py<br/>zero-pad district IDs ·<br/>snake_case 140 columns"]
    P1 --> CSV["data/texas_finance_clean.csv<br/>(gitignored, 20,587 rows)"]
    CSV --> P2["scripts/import_to_supabase.py<br/>dtype district_number=str"]
    P2 --> T["texas_school_finance table"]
    T --> S1["sql/create_tables.sql<br/>PK · indexes · views ·<br/>matview · RLS · grants"]
    T --> S2["sql/create_breakdown_view.sql<br/>9 MECE spending categories"]
    S1 --> RF["REFRESH MATERIALIZED VIEW<br/>v_anomaly_flags<br/>(required after every import)"]
    RF --> API2["API + dashboard serve it"]
    API2 --> OUT["Exports leave the system:<br/>CSV · PNG · print PDF"]
```

## 6. Deployment Workflow

```mermaid
graph LR
    DEV["git push"] --> CI["GitHub Actions<br/>.github/workflows/ci.yml<br/>ruff + pytest × Py 3.10/3.11/3.12"]
    CI -->|green| M["master"]
    M --> D1["✅ ACTIVE: Vercel REST API deploy<br/>swaps requirements-vercel.txt<br/>env: SUPABASE_DB_URL (pooler :6543) ·<br/>OPENAI_API_KEY"]
    M --> D2["🔵 CONFIGURED: render.yaml<br/>one-click blueprint (unexercised)"]
    M --> D3["🔵 CONFIGURED: Dockerfile<br/>any VPS (unexercised)"]
    D1 --> PROD["https://texas-isd-finances.vercel.app<br/>GET /health = healthy"]
```

## 7. Revenue-Generation Workflow

Honest status: **the product currently earns $0 by design** (MIT, free,
no payment rail, no auth, no analytics). The funnel below shows which
stages exist today (✅) and which are documented plans only (🔵).

```mermaid
graph TB
    A["Attention 🟡<br/>live site exists; no marketing,<br/>no analytics to measure reach"] --> B["Lead capture 🔴<br/>no email capture, no accounts —<br/>visitors are anonymous"]
    B --> C["Qualification 🔵<br/>planned: API-key signup separates<br/>casual visitors from data buyers"]
    C --> D["Engagement ✅<br/>dashboard + exports + NLP —<br/>the working free tier"]
    D --> E["Conversion 🔵<br/>planned: paid API keys ·<br/>bulk exports · alert subscriptions"]
    E --> F["Follow-up 🔴<br/>no CRM, no email system"]
    F --> G["Sale 🔵<br/>4 documented paths: freemium API ·<br/>reports/briefs · grants ·<br/>consulting wedge (PROJECT_MAP.md)"]
    G --> H["Retention 🟡<br/>district remembered per device;<br/>yearly TEA refresh brings users back"]
    H --> I["Expansion 🔵<br/>other states use the same<br/>pipeline pattern"]
```

---

## Component Inventory (verified, with status)

### Application & data

| Component | Path | Status | Notes |
|---|---|---|---|
| FastAPI service (11 routes) | `src/api.py` | ✅ | Live; lifespan pool, CORS, rate limit |
| Dashboard UI | `static/index.html` | ✅ | v3 white-minimalist; no build step |
| NLP agent | `src/nlp_engine.py` | ✅ | LangChain 1.x `create_agent`; view-scoped |
| Vercel entrypoint | `api/index.py`, `vercel.json` | ✅ | Active production path |
| Supabase DB | project `zwhvabkvrexphlskubog` (us-east-1) | ✅ | 20,587 rows; RLS on base table |
| Schema + views | `sql/create_tables.sql`, `sql/create_breakdown_view.sql` | ✅ | Import-first order (documented) |
| Data prep | `scripts/prepare_data.py` | ✅ | Tested helpers |
| Data import | `scripts/import_to_supabase.py` | ✅ | Leading-zero-safe |
| UX simulation | `scripts/simulate_admin_usage.py` | ✅ | Seeded; results in `docs/simulation_results.json` |
| Chart helper library | `src/visualizations.py` | 🟡 | Works & tested, but **not used by the API or UI** — offline analysis only |
| Sample queries module | `src/sample_queries.py` | ✅ | Dependency-free |

### Operations & quality

| Component | Path | Status | Notes |
|---|---|---|---|
| CI (ruff + pytest ×3 Pythons) | `.github/workflows/ci.yml` | ✅ | Enforcing; green on master |
| Test suite (29 tests) | `tests/` | ✅ | Runs with zero credentials |
| Rate limiter on /query | `src/api.py` `_rate_limited` | 🟡 | Works; per-serverless-instance, not global |
| Render blueprint | `render.yaml` | 🔵 | Spec-validated, never executed |
| Docker image | `Dockerfile`, `.dockerignore` | 🔵 | Written, never built in anger |
| Type checking | — | 🔴 | No mypy/pyright configured |
| Monitoring / uptime alerts | — | 🔴 | Only manual `/health` checks |
| Analytics | — | 🔴 | No usage measurement at all |

### Documentation & memory

| Component | Path | Status |
|---|---|---|
| Boot file + session memory | `CLAUDE.md`, `docs/ENGINEERING_LOG.md`, `.claude/skills/ariba/SKILL.md` | ✅ |
| Audit trail (3 rounds) | `AUDIT.md` | ✅ |
| UX research + tutorial | `docs/UX_RESEARCH.md`, `docs/TUTORIAL.md` | ✅ |
| Launch runbook | `DEPLOYMENT.md`, `RUNBOOK.md` | ✅ |
| Env reference | `ENVIRONMENT.md`, `env_template.txt` | ✅ |
| This blueprint | `REPO_MAP.md`, `ARCHITECTURE.md`, `AGENTS.md` | ✅ |

### External services

| Service | Role | Status | Evidence |
|---|---|---|---|
| Vercel (`tag-ai` / project `texas-isd-finances`) | Hosting | ✅ | `/health` returns healthy |
| Supabase (org GOAT-UIX) | Postgres + REST | ✅ | Live queries |
| OpenAI (gpt-4o-mini) | NLP model | ✅ | Live `/query` verified |
| TEA (tea.texas.gov) | Data source | ✅ | Current release ingested |
| GitHub Actions | CI | ✅ | Green check runs |
| Authentication provider | — | 🔴 none | Public read-only by design; becomes required for any paid tier |
| Queues / schedulers / webhooks | — | 🔴 none | Data refresh is manual, once per TEA release |

### Potentially obsolete (evidence before removal)

| Item | Evidence | Risk of removal |
|---|---|---|
| 🗑️ `src/visualizations.py` | No imports from `src/api.py` or `static/`; only `tests/test_visualizations.py` references it | Low risk to the app — but it's the only Python charting utility for offline reports (a documented revenue path). **Keep** until the reports product is decided. |
| 🗑️ matplotlib/seaborn/plotly in `requirements.txt` | Only used by `src/visualizations.py` | Removing shrinks local installs; keep while the file stays. Already excluded from production deploys via `requirements-vercel.txt`. |

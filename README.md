# Texas ISD Financial Data Portal

A public transparency system for analyzing Texas Independent School District
financial data (2009–2025), featuring a citizen-friendly web portal, natural
language querying, and automatic anomaly detection.

🌐 **Live portal:** https://texas-isd-finances.vercel.app

🗺️ **New here?** See [PROJECT_MAP.md](PROJECT_MAP.md) for a visual,
plain-English map of the whole system.

## 🎯 Project Goals

- **Scalable Oversight**: AI-powered anomaly detection across 1000+ districts
- **Public Accountability**: Citizen-friendly portal for viewing district finances
- **Policy Feedback**: Data-driven insights for legislators and policymakers

## 🚀 Quick Start

See [QUICKSTART.md](QUICKSTART.md) for local setup and
[DEPLOYMENT.md](DEPLOYMENT.md) for taking it public.

### Prerequisites
- Python 3.10+
- Supabase account (free tier works)
- OpenAI API key (only for natural-language queries)
- TEA Excel data file (2009–2025 summarized financial data)

### Basic Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp env_template.txt .env
# Edit .env with your credentials

# 3. Prepare and import data (see DEPLOYMENT.md)
python scripts/prepare_data.py
python scripts/import_to_supabase.py

# 4. Start the API + portal
uvicorn src.api:app --reload
```

Then open http://localhost:8000/ for the portal, or
http://localhost:8000/docs for the API documentation.

## 📁 Project Structure

```
texas-isd-finances/
├── api/                    # Vercel serverless entrypoint
├── scripts/                # Data preparation and import
│   ├── prepare_data.py     # Excel → clean CSV converter
│   └── import_to_supabase.py
├── sql/
│   └── create_tables.sql   # Tables, views, indexes, RLS, grants
├── src/
│   ├── api.py              # FastAPI service (serves portal + API)
│   ├── nlp_engine.py       # Natural language → SQL (LangChain)
│   └── visualizations.py   # Chart generation helpers
├── static/
│   └── index.html          # Public portal (no build step needed)
├── tests/                  # Pytest suite (runs without credentials)
├── Dockerfile              # Container deployment
├── render.yaml             # One-click Render blueprint
├── DEPLOYMENT.md           # Public launch guide
└── AUDIT.md                # Pre-launch audit report (June 2026)
```

## 🔧 Key Features

### Administrator Dashboard
A dependency-free single-page dashboard served at `/`, designed from a
Monte Carlo simulation of 1,000 Texas school administrators
([docs/UX_RESEARCH.md](docs/UX_RESEARCH.md)): KPI tiles with plain-English
captions, 17-year trends vs the statewide median, similar-size peer
comparison, spending breakdown, anomaly explanations, guided tutorial,
print/CSV export for board packets, and a plain-English question box.
User guide: [docs/TUTORIAL.md](docs/TUTORIAL.md).

### Natural Language Queries
Ask questions in plain English:
- "Show Dallas ISD spending per student 2020-2024"
- "Which districts have declining enrollment?"
- "Find anomalies in Houston area districts"

### Anomaly Detection
Automatic flagging of:
- Revenue drops >15% year-over-year
- Spending spikes >20% with flat enrollment
- Per-student spending increases >15%
- Enrollment declines >10%

### API Endpoints
- `POST /query` — Natural language queries
- `GET /districts` — List/search districts
- `GET /district/{id}/summary` — District financials
- `GET /district/{id}/peers` — Similar-size peer comparison + percentile
- `GET /benchmarks` — Statewide medians per year
- `GET /anomalies` — Flagged anomalies (filterable by district)
- `GET /stats` — Statewide statistics
- `GET /health` — Service health

## 📊 Data Schema

Main table: `texas_school_finance`
- 140+ financial metrics per district/year
- Primary key: (district_number, year)
- Covers: Revenue, expenditures, enrollment, debt

Public views:
- `v_finance_summary` — Simplified read-only view
- `v_anomaly_flags` — Detected anomalies (materialized; refresh after imports)

Source: Texas Education Agency (TEA) summarized financial data, PEIMS.

## 🔒 Security

- Row-level security enabled on the base table; API roles read only the views
- Read-only public views; NLP agent is restricted to those views
- CORS locked to GET/POST; origins configurable via `CORS_ALLOW_ORIGINS`
- No credentials in the repository — everything via environment variables

## 🚀 Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md). Supported targets:

1. **Render** — one-click blueprint (`render.yaml`)
2. **Docker** — Railway, Fly.io, or any VPS (`Dockerfile`)
3. **Vercel** — portal + data API (`vercel.json`, `api/index.py`)

Database: Supabase (managed Postgres, free tier).

## 🧪 Development

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

CI runs both on every push and pull request (Python 3.10–3.12).

## 📝 License

[MIT](LICENSE) — free to use, modify, and redistribute. This project exists
to promote transparency in Texas education funding.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Contributions that enhance public
access and understanding are welcome.

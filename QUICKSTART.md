# Texas ISD Finance Portal — Quick Start Guide

## Prerequisites
- Python 3.10+
- Supabase account
- OpenAI API key (only needed for natural-language queries)
- TEA Excel file: `2008-2024-summarized-financial-data-03-17-2025.xlsx`

## Step-by-Step Setup

### 1. Clone and Setup Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate — macOS/Linux:
source .venv/bin/activate
# Activate — Windows:
#   .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
# Copy template and fill in your credentials (macOS/Linux)
cp env_template.txt .env
# Windows: copy env_template.txt .env

# Edit .env with your Supabase and OpenAI credentials
```

### 3. Prepare Data
```bash
# Place your Excel file in the project root, then:
python scripts/prepare_data.py
```

### 4. Setup Supabase
1. Create a new project at https://app.supabase.com
2. Open the SQL Editor
3. Run the contents of `sql/create_tables.sql`
4. Import the data: `python scripts/import_to_supabase.py`
5. In the SQL Editor: `REFRESH MATERIALIZED VIEW public.v_anomaly_flags;`

### 5. Test the NLP Engine (optional)
```bash
python -m src.nlp_engine
```

### 6. Start the API + Portal
```bash
uvicorn src.api:app --reload --port 8000
```

### 7. Try It
- Portal: http://localhost:8000/
- Interactive API docs: http://localhost:8000/docs

The app starts even before the database is configured — the portal will show
a "database not connected" banner and data endpoints return 503 until
`SUPABASE_DB_URL` is set.

## Sample API Calls

### Natural Language Query
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "Show Dallas ISD spending per student 2020-2024"}'
```

### List Districts
```bash
curl "http://localhost:8000/districts?search=Dallas"
```

### Get Anomalies
```bash
curl "http://localhost:8000/anomalies?year=2024"
```

## Next Steps
See [DEPLOYMENT.md](DEPLOYMENT.md) to deploy publicly (Render, Docker, or
Vercel) and for production security notes.

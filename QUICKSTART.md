# Texas ISD Finance Portal - Quick Start Guide

## Prerequisites
- Python 3.8+
- Supabase account
- OpenAI API key
- Excel file: `2008-2024-summarized-financial-data-03-17-2025.xlsx`

## Step-by-Step Setup

### 1. Clone and Setup Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
# Copy template and fill in your credentials
copy env_template.txt .env
# Edit .env with your Supabase and OpenAI credentials
```

### 3. Prepare Data
```bash
# Place your Excel file in project root
# Run data preparation
python scripts/prepare_data.py
```

### 4. Setup Supabase
1. Create new project at https://app.supabase.com
2. Open SQL Editor
3. Run contents of `sql/create_tables.sql`
4. Import `data/texas_finance_clean.csv` via Table Editor

### 5. Test NLP Engine
```bash
python src/nlp_engine.py
```

### 6. Start API Server
```bash
uvicorn src.api:app --reload --port 8000
```

### 7. Test API
Visit http://localhost:8000/docs for interactive API documentation

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
1. Deploy API to cloud (Railway, Render, etc.)
2. Build frontend portal
3. Add authentication for admin features
4. Schedule data refresh jobs
5. Implement advanced visualizations

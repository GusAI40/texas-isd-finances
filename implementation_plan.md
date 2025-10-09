# Texas ISD Financial Data Implementation Plan

## Phase 1: Environment Setup

### Local Setup
- Create project directory: `mkdir texas-isd-finances && cd texas-isd-finances`
- Create Python virtual environment: `python -m venv .venv`
- Activate venv: `.venv\Scripts\activate` (Windows)
- Create `.env` file for credentials
- Create `.gitignore` with `.env`, `.venv/`, `*.csv`, `*.xlsx`

### Install Dependencies
```bash
pip install pandas openpyxl sqlalchemy psycopg2-binary
pip install langchain langchain-community langchain-openai
pip install llama-index llama-index-llms-openai
pip install fastapi uvicorn python-dotenv
pip install matplotlib seaborn plotly
```

## Phase 2: Data Preparation

### Download and Clean Data
- Place `2008-2024-summarized-financial-data-03-17-2025.xlsx` in project root
- Create `scripts/prepare_data.py`
- Run data cleaning script to generate:
  - `data/texas_finance_clean.csv`
  - `sql/create_tables.sql`
  - `data/data_dictionary.csv`

## Phase 3: Supabase Setup

### Create Supabase Project
- Go to https://app.supabase.com
- Create new project (note down password)
- Wait for project to initialize
- Go to Settings → Database → Connection Info
- Copy connection string to `.env`:
  ```
  SUPABASE_DB_URL="postgresql://postgres:[YOUR-PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres"
  SUPABASE_ANON_KEY="[YOUR-ANON-KEY]"
  SUPABASE_URL="https://[PROJECT-REF].supabase.co"
  ```

### Create Database Schema
- Open SQL Editor in Supabase
- Run `sql/create_tables.sql`
- Verify table created: `texas_school_finance`

### Import Data
- Table Editor → texas_school_finance → Import
- Upload `data/texas_finance_clean.csv`
- Map columns (should auto-match)
- Import data

## Phase 4: Create Views

### Public Access Views
- SQL Editor → New Query
- Run:
  ```sql
  CREATE OR REPLACE VIEW public.v_finance_summary AS
  SELECT
    district_number,
    district_name,
    year,
    all_funds_total_operating_revenue AS total_revenue,
    all_funds_total_disbursements AS total_spend,
    fall_survey_enrollment AS enrollment,
    ROUND((all_funds_total_disbursements / NULLIF(fall_survey_enrollment,0))::numeric, 2) AS spend_per_student
  FROM public.texas_school_finance;
  ```

### Anomaly Detection View
- Create anomaly flags view:
  ```sql
  CREATE MATERIALIZED VIEW public.v_anomaly_flags AS
  SELECT 
    district_number,
    year,
    -- Flag 1: Revenue drop > 15%
    CASE WHEN (total_revenue - LAG(total_revenue) OVER w) / NULLIF(LAG(total_revenue) OVER w, 0) < -0.15 
         THEN true ELSE false END AS revenue_drop_flag,
    -- Flag 2: Spending spike with flat enrollment
    CASE WHEN (total_spend - LAG(total_spend) OVER w) / NULLIF(LAG(total_spend) OVER w, 0) > 0.20
         AND ABS(enrollment - LAG(enrollment) OVER w) < 10
         THEN true ELSE false END AS spend_spike_flag
  FROM v_finance_summary
  WINDOW w AS (PARTITION BY district_number ORDER BY year);
  ```

## Phase 5: Security Setup

### Create Read-Only Role
```sql
CREATE ROLE app_readonly LOGIN PASSWORD 'secure_password_here';
GRANT CONNECT ON DATABASE postgres TO app_readonly;
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON public.v_finance_summary TO app_readonly;
GRANT SELECT ON public.v_anomaly_flags TO app_readonly;
```

### Enable RLS
```sql
ALTER TABLE texas_school_finance ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read" ON v_finance_summary FOR SELECT USING (true);
```

## Phase 6: NLP Integration

### Create NLP Query Engine
- Create `src/nlp_engine.py`
- Add OpenAI API key to `.env`: `OPENAI_API_KEY="sk-..."`
- Implement LangChain SQL agent
- Test with: "Show Dallas ISD spending per student 2020-2024"

## Phase 7: API Development

### FastAPI Service
- Create `src/api.py`
- Endpoints:
  - `GET /districts` - list all districts
  - `GET /query` - NLP query endpoint
  - `GET /district/{id}/summary` - district financial summary
  - `GET /anomalies` - flagged anomalies

### Run API
```bash
uvicorn src.api:app --reload --port 8000
```

## Phase 8: Frontend (Optional)

### Next.js Setup
```bash
npx create-next-app@latest texas-isd-portal --typescript --tailwind
cd texas-isd-portal
npm install @supabase/supabase-js recharts
```

### Create Components
- `DistrictSearch.tsx` - district selector
- `FinanceChart.tsx` - spending trends
- `AnomalyList.tsx` - flagged issues
- `NLPQuery.tsx` - natural language search

## Phase 9: Deployment

### Backend
- Deploy API to Railway/Render/Fly.io
- Set environment variables
- Configure CORS for frontend

### Frontend
- Deploy to Vercel
- Configure Supabase client with anon key
- Set API endpoint

## Phase 10: Testing & Documentation

### Test Queries
- "Which district has highest debt per student?"
- "Show Austin ISD budget trend 2015-2020"
- "Find districts with declining enrollment but increasing spending"

### Document
- API endpoints
- Schema reference
- Sample queries
- Anomaly flag definitions

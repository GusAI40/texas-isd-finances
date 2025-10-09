# ⚡ Quick Start Checklist - Texas ISD Finance Portal

## 🚀 Execute These Steps in Order

### ✅ Step 1: Environment Setup (5 minutes)

```bash
# 1. Check if .env file exists
dir .env

# 2. If not, create from template
copy env_template.txt .env

# 3. Verify all credentials are present
type .env
```

**Required Variables**:
- ✅ `SUPABASE_DB_URL` - Already configured
- ✅ `SUPABASE_URL` - Already configured  
- ✅ `SUPABASE_ANON_KEY` - Already configured
- ✅ `OPENAI_API_KEY` - Already configured

---

### ✅ Step 2: Python Environment (10 minutes)

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment (Windows)
.venv\Scripts\activate

# 3. Upgrade pip
python -m pip install --upgrade pip

# 4. Install all dependencies
pip install -r requirements.txt

# 5. Verify installation
pip list
```

**Expected Packages** (26 total):
- pandas, openpyxl
- sqlalchemy, psycopg2-binary, asyncpg
- langchain, langchain-openai, openai
- fastapi, uvicorn, pydantic
- matplotlib, seaborn, plotly

---

### ✅ Step 3: Verify Data Files (2 minutes)

```bash
# Check if data files exist
dir data\texas_finance_clean.csv
dir data\data_dictionary.csv
dir ETL_2008-2024-summarized-financial-data-03-17-2025.xlsx
```

**Expected Output**:
- ✅ `texas_finance_clean.csv` (18.8 MB) - **CONFIRMED**
- ✅ `data_dictionary.csv` (8.8 KB) - **CONFIRMED**
- ✅ Source Excel file (19.4 MB) - **CONFIRMED**

---

### ✅ Step 4: Supabase Database Setup (15 minutes)

#### 4.1: Access Supabase
1. Go to: https://app.supabase.com
2. Login to project: `emtwbizmorqwhboebgzw`
3. Navigate to: **SQL Editor**

#### 4.2: Create Database Schema
```sql
-- Copy entire contents of sql/create_tables.sql
-- Paste into SQL Editor
-- Click "Run" (or press Ctrl+Enter)
```

**This Creates**:
- ✅ Table: `texas_school_finance` (main data)
- ✅ View: `v_finance_summary` (public access)
- ✅ Materialized View: `v_anomaly_flags` (anomaly detection)
- ✅ Indexes for performance
- ✅ Permissions for anon/authenticated users

#### 4.3: Verify Schema Creation
```sql
-- Run this to verify
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('texas_school_finance', 'v_finance_summary', 'v_anomaly_flags');
```

**Expected Result**: 3 rows returned

---

### ✅ Step 5: Import Financial Data (10 minutes)

#### Method 1: Supabase Table Editor (Recommended)
1. Navigate to: **Table Editor** → `texas_school_finance`
2. Click: **Insert** → **Import data from CSV**
3. Upload: `data/texas_finance_clean.csv`
4. Verify column mapping (should auto-match)
5. Click: **Import**
6. Wait for completion (may take 2-3 minutes)

#### Method 2: Python Script (Alternative)
```bash
# Activate virtual environment first
.venv\Scripts\activate

# Create and run import script
python -c "
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('SUPABASE_DB_URL'))

df = pd.read_csv('data/texas_finance_clean.csv')
df.to_sql('texas_school_finance', engine, if_exists='append', index=False, chunksize=1000)
print(f'Imported {len(df)} records successfully!')
"
```

#### 5.3: Verify Data Import
```sql
-- Check record count
SELECT COUNT(*) as total_records FROM texas_school_finance;

-- Check year range
SELECT MIN(year) as start_year, MAX(year) as end_year FROM texas_school_finance;

-- Check district count
SELECT COUNT(DISTINCT district_number) as total_districts FROM texas_school_finance;

-- Sample data
SELECT * FROM v_finance_summary WHERE district_name ILIKE '%DALLAS%' LIMIT 5;
```

**Expected Results**:
- Total records: ~17,000+ rows
- Year range: 2008 to 2024
- Total districts: 1,000+ districts
- Dallas ISD data visible

---

### ✅ Step 6: Test NLP Engine (5 minutes)

```bash
# Ensure virtual environment is active
.venv\Scripts\activate

# Run NLP engine test
python src/nlp_engine.py
```

**Expected Output**:
```
Query: Show me Dallas ISD spending per student from 2018 to 2023
--------------------------------------------------
Answer: [SQL results showing Dallas ISD data]

Query: Which districts have anomaly flags in 2024?
--------------------------------------------------
Answer: [List of districts with anomalies]

Query: What's the average enrollment across all districts?
--------------------------------------------------
Answer: [Average enrollment number]
```

**If Errors Occur**:
- ❌ Connection error → Check `SUPABASE_DB_URL` in `.env`
- ❌ OpenAI error → Verify `OPENAI_API_KEY` is valid
- ❌ SQL error → Ensure views exist in database

---

### ✅ Step 7: Start API Server (3 minutes)

```bash
# Ensure virtual environment is active
.venv\Scripts\activate

# Start FastAPI server
uvicorn src.api:app --reload --port 8000
```

**Expected Output**:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Access Points**:
- 🌐 API Root: http://localhost:8000
- 📚 Swagger Docs: http://localhost:8000/docs
- 📖 ReDoc: http://localhost:8000/redoc

---

### ✅ Step 8: Test API Endpoints (10 minutes)

Open a **new terminal** (keep server running) and test:

#### 8.1: Health Check
```bash
curl http://localhost:8000/health
```
**Expected**: `{"status":"healthy","database":"connected"}`

#### 8.2: Database Statistics
```bash
curl http://localhost:8000/stats
```
**Expected**: JSON with `total_districts`, `total_years`, `avg_spend_per_student`

#### 8.3: Search Districts
```bash
curl "http://localhost:8000/districts?search=Dallas&limit=5"
```
**Expected**: Array of Dallas-area districts

#### 8.4: District Summary
```bash
curl "http://localhost:8000/district/057905/summary?start_year=2020&end_year=2024"
```
**Expected**: Dallas ISD financial data 2020-2024

#### 8.5: Natural Language Query
```bash
curl -X POST "http://localhost:8000/query" -H "Content-Type: application/json" -d "{\"question\": \"Show Dallas ISD spending per student 2020-2024\"}"
```
**Expected**: NLP-generated answer with data

#### 8.6: Anomaly Detection
```bash
curl "http://localhost:8000/anomalies?year=2024&limit=10"
```
**Expected**: Districts with anomaly flags in 2024

#### 8.7: Sample Queries
```bash
curl http://localhost:8000/sample-queries
```
**Expected**: List of example natural language queries

---

### ✅ Step 9: Interactive API Testing (5 minutes)

1. Open browser: http://localhost:8000/docs
2. Explore Swagger UI with interactive API documentation
3. Try these endpoints:
   - `GET /districts` - List all districts
   - `POST /query` - Natural language query
   - `GET /anomalies` - View flagged anomalies
   - `GET /stats` - Database statistics

---

## 🎯 Success Criteria

### ✅ System is Ready When:
- [ ] Virtual environment activated
- [ ] All Python packages installed
- [ ] Database schema created in Supabase
- [ ] Financial data imported (17,000+ records)
- [ ] NLP engine returns valid results
- [ ] API server running on port 8000
- [ ] All 7 API endpoints responding correctly
- [ ] Swagger docs accessible at /docs

---

## 🐛 Troubleshooting

### Issue: Virtual Environment Won't Activate
```bash
# Try PowerShell execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then activate again
.venv\Scripts\activate
```

### Issue: Package Installation Fails
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Install packages one by one
pip install pandas openpyxl
pip install sqlalchemy psycopg2-binary asyncpg
pip install langchain langchain-openai openai
pip install fastapi uvicorn pydantic
```

### Issue: Database Connection Error
```bash
# Test connection string
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('SUPABASE_DB_URL'))"

# Verify format: postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres
```

### Issue: OpenAI API Error
```bash
# Verify API key
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('OPENAI_API_KEY')[:20] + '...')"

# Test OpenAI connection
python -c "from openai import OpenAI; import os; from dotenv import load_dotenv; load_dotenv(); client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')); print('OpenAI connection successful!')"
```

### Issue: Data Import Fails
```bash
# Check CSV file integrity
python -c "import pandas as pd; df = pd.read_csv('data/texas_finance_clean.csv'); print(f'Rows: {len(df)}, Columns: {len(df.columns)}')"

# Verify column names match schema
python -c "import pandas as pd; df = pd.read_csv('data/texas_finance_clean.csv'); print(df.columns.tolist()[:10])"
```

---

## 📊 Expected Results Summary

### Database
- **Records**: 17,000+ financial records
- **Districts**: 1,000+ Texas ISDs
- **Years**: 2008-2024 (17 years)
- **Metrics**: 140+ financial indicators per record

### API Performance
- **Response Time**: < 500ms (p95)
- **Concurrent Users**: 10+ simultaneous queries
- **Uptime**: 99.9% availability target

### NLP Capabilities
- **Query Types**: Trends, comparisons, anomalies, summaries
- **Accuracy**: 90%+ correct SQL generation
- **Languages**: Natural English questions

---

## 🚀 Next Steps After Setup

1. **Explore Sample Queries**:
   - "Which district has highest spending per student in 2024?"
   - "Show me all districts with revenue drops in 2023"
   - "Compare Houston ISD and Austin ISD budgets"

2. **Review Anomaly Flags**:
   - Check districts with spending spikes
   - Identify enrollment decline patterns
   - Analyze revenue drop trends

3. **Plan Frontend Development**:
   - Design public transparency portal
   - Create interactive visualizations
   - Build citizen-friendly interface

4. **Prepare for Deployment**:
   - Choose hosting platform (Railway/Render)
   - Configure production environment
   - Set up monitoring and alerts

---

**Estimated Total Time**: 60-75 minutes
**Difficulty Level**: Intermediate
**Prerequisites**: Python 3.8+, Supabase account, OpenAI API key

---

**Last Updated**: 2025-10-06
**Status**: Ready for Execution ✅

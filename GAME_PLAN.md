# 🎯 Texas ISD Financial Data Portal - Game Plan

## 📊 Project Overview

**Mission**: Create a comprehensive AI-powered system for analyzing Texas Independent School District financial data (2008-2024) with natural language querying, anomaly detection, and public transparency tools.

**Current Status**: ✅ Foundation Complete
- Data preparation scripts: ✅ Ready
- Database schema: ✅ Designed
- API endpoints: ✅ Coded
- NLP engine: ✅ Implemented
- **Next**: Environment setup and deployment

---

## 🏗️ System Architecture

### Technology Stack
- **Backend**: Python 3.8+ with FastAPI
- **Database**: Supabase (PostgreSQL)
- **AI/NLP**: OpenAI GPT-4o-mini + LangChain
- **Frontend** (Phase 2): Next.js + TypeScript + Tailwind CSS
- **Deployment**: Railway/Render (API) + Vercel (Frontend)

### Data Pipeline
```
Excel File (19MB) 
  → prepare_data.py 
  → texas_finance_clean.csv 
  → Supabase PostgreSQL 
  → API + NLP Engine 
  → Public Portal
```

### Key Features
1. **Natural Language Queries**: "Show Dallas ISD spending per student 2020-2024"
2. **Anomaly Detection**: Auto-flag revenue drops, spending spikes, enrollment declines
3. **Public API**: RESTful endpoints for transparency
4. **Visualizations**: Charts, trends, comparisons

---

## 🚀 Phase 1: Core System Setup (Days 1-3)

### Day 1: Environment & Data Setup

#### ✅ Task 1.1: Verify Environment Configuration
**Status**: NEEDS VERIFICATION
```bash
# Check if .env file exists
# Should contain:
# - SUPABASE_DB_URL
# - SUPABASE_URL  
# - SUPABASE_ANON_KEY
# - OPENAI_API_KEY
```

**Action Items**:
- [ ] Verify `.env` file exists in project root
- [ ] Confirm all 4 environment variables are populated
- [ ] Test Supabase connection string format
- [ ] Validate OpenAI API key is active

#### ✅ Task 1.2: Python Environment Setup
**Status**: PENDING
```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Expected Packages**:
- pandas, openpyxl (data processing)
- sqlalchemy, psycopg2-binary, asyncpg (database)
- langchain, langchain-openai (NLP)
- fastapi, uvicorn (API)
- matplotlib, seaborn, plotly (visualizations)

#### ✅ Task 1.3: Data Preparation Verification
**Status**: ✅ COMPLETE (files exist)
```bash
# Verify cleaned data exists
ls data/texas_finance_clean.csv
ls data/data_dictionary.csv
```

**Confirmed**:
- ✅ `texas_finance_clean.csv` (18.8MB) - Ready
- ✅ `data_dictionary.csv` (8.8KB) - Ready
- ✅ Source Excel file present

---

### Day 2: Database Setup

#### ✅ Task 2.1: Supabase Project Configuration
**Status**: ✅ CREDENTIALS READY

**Supabase Details** (from env_template.txt):
- URL: `https://emtwbizmorqwhboebgzw.supabase.co`
- Database: `db.emtwbizmorqwhboebgzw.supabase.co:5432`
- Project Ref: `emtwbizmorqwhboebgzw`

**Action Items**:
- [x] Supabase project created
- [ ] Verify project is active and accessible
- [ ] Open SQL Editor in Supabase dashboard

#### ✅ Task 2.2: Execute Database Schema
**Status**: PENDING
```sql
-- Run in Supabase SQL Editor
-- File: sql/create_tables.sql
```

**What This Creates**:
1. **Main Table**: `texas_school_finance`
   - 140+ financial metrics per district/year
   - Primary key: (district_number, year)
   - Indexes on year, district_number, district_name

2. **Summary View**: `v_finance_summary`
   - Simplified public-facing data
   - Calculated fields: spend_per_student, revenue_per_student
   - Read-only access for safety

3. **Anomaly View**: `v_anomaly_flags` (Materialized)
   - Auto-detects: revenue drops >15%, spending spikes >20%
   - Enrollment declines >10%, per-student increases >15%
   - Includes year-over-year comparisons

**Verification**:
```sql
-- After running create_tables.sql, verify:
SELECT COUNT(*) FROM information_schema.tables 
WHERE table_name IN ('texas_school_finance', 'v_finance_summary', 'v_anomaly_flags');
-- Should return 3
```

#### ✅ Task 2.3: Import Financial Data
**Status**: PENDING

**Method 1: Supabase Table Editor (Recommended)**
1. Navigate to Table Editor → `texas_school_finance`
2. Click "Insert" → "Import data from CSV"
3. Upload `data/texas_finance_clean.csv`
4. Map columns (should auto-match)
5. Import data

**Method 2: Python Script (Alternative)**
```python
# Create scripts/import_to_supabase.py
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("SUPABASE_DB_URL"))

df = pd.read_csv("data/texas_finance_clean.csv")
df.to_sql("texas_school_finance", engine, if_exists="append", index=False)
```

**Verification**:
```sql
-- Check record count
SELECT COUNT(*) FROM texas_school_finance;

-- Check year range
SELECT MIN(year), MAX(year) FROM texas_school_finance;

-- Check district count
SELECT COUNT(DISTINCT district_number) FROM texas_school_finance;
```

---

### Day 3: API & NLP Testing

#### ✅ Task 3.1: Test NLP Engine
**Status**: PENDING
```bash
# Activate virtual environment
.venv\Scripts\activate

# Run NLP engine test
python src/nlp_engine.py
```

**Expected Output**:
- Successful database connection
- LangChain agent initialization
- Sample query results for:
  - "Show me Dallas ISD spending per student from 2018 to 2023"
  - "Which districts have anomaly flags in 2024?"
  - "What's the average enrollment across all districts?"

**Troubleshooting**:
- If connection fails: Check `SUPABASE_DB_URL` in `.env`
- If OpenAI fails: Verify `OPENAI_API_KEY` is valid
- If SQL errors: Ensure views exist in database

#### ✅ Task 3.2: Start FastAPI Server
**Status**: PENDING
```bash
# Start development server
uvicorn src.api:app --reload --port 8000
```

**Expected Behavior**:
- Server starts on `http://localhost:8000`
- Database connection pool initialized
- Swagger docs available at `http://localhost:8000/docs`

#### ✅ Task 3.3: Test API Endpoints
**Status**: PENDING

**Test Sequence**:

1. **Health Check**
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "database": "connected"}
```

2. **Database Stats**
```bash
curl http://localhost:8000/stats
# Expected: total_districts, total_years, avg_spend_per_student
```

3. **List Districts**
```bash
curl "http://localhost:8000/districts?search=Dallas&limit=10"
# Expected: Array of Dallas-area districts
```

4. **District Summary**
```bash
curl "http://localhost:8000/district/057905/summary?start_year=2020&end_year=2024"
# Expected: Dallas ISD financial data 2020-2024
```

5. **Natural Language Query**
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "Show Dallas ISD spending per student 2020-2024"}'
# Expected: NLP-generated SQL result with answer
```

6. **Anomaly Detection**
```bash
curl "http://localhost:8000/anomalies?year=2024&limit=20"
# Expected: Districts with flagged anomalies in 2024
```

---

## 🎨 Phase 2: Schema Enforcement & Best Practices (Days 4-5)

### Windsurf Rules v10x+ Compliance

#### ✅ Task 4.1: Create Pydantic Models
**Status**: PENDING
**File**: `schemas/pydantic_models.py`

```python
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class DistrictFinance(BaseModel):
    """Texas School District Financial Record"""
    district_number: str = Field(..., regex=r'^\d{6}$')
    district_name: str
    year: int = Field(..., ge=2008, le=2024)
    total_revenue: Optional[float] = Field(None, ge=0)
    total_spend: Optional[float] = Field(None, ge=0)
    enrollment: Optional[int] = Field(None, ge=0)
    spend_per_student: Optional[float] = Field(None, ge=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "district_number": "057905",
                "district_name": "DALLAS ISD",
                "year": 2024,
                "total_revenue": 1500000000,
                "total_spend": 1450000000,
                "enrollment": 145000,
                "spend_per_student": 10000
            }
        }

class AnomalyFlag(BaseModel):
    """Financial Anomaly Detection Result"""
    district_number: str
    district_name: str
    year: int
    revenue_drop_flag: bool
    spend_spike_flag: bool
    per_student_spike_flag: bool
    enrollment_decline_flag: bool
    
class NLPQuery(BaseModel):
    """Natural Language Query Request"""
    question: str = Field(..., min_length=10, max_length=500)
    max_results: int = Field(100, ge=1, le=500)
```

#### ✅ Task 4.2: Add Input Validation
**Status**: PENDING

**Update API endpoints** to use Pydantic models:
- Replace generic `Dict` types with specific models
- Add validation for district_number format (6 digits)
- Enforce year range constraints (2008-2024)
- Validate numeric fields are non-negative

#### ✅ Task 4.3: Create Agent Framework
**Status**: PENDING
**File**: `src/agents/architect_agent.py`

```python
"""
ArchitectAgent: Designs optimal queries for financial analysis
"""
from pydantic import BaseModel
from typing import List, Dict

class QueryStrategy(BaseModel):
    query_type: str  # "trend", "comparison", "anomaly", "summary"
    tables_needed: List[str]
    filters: Dict[str, any]
    aggregations: List[str]
    
class ArchitectAgent:
    def design_query(self, user_question: str) -> QueryStrategy:
        """Analyze question and design optimal query strategy"""
        # Implement query planning logic
        pass
```

---

## 🌐 Phase 3: Frontend Development (Days 6-8)

### Next.js Public Portal

#### ✅ Task 5.1: Initialize Next.js Project
**Status**: PENDING
```bash
npx create-next-app@latest texas-isd-portal --typescript --tailwind --app
cd texas-isd-portal
npm install @supabase/supabase-js recharts lucide-react
```

#### ✅ Task 5.2: Create Core Components
**Status**: PENDING

**Component Structure**:
```
app/
├── page.tsx                    # Landing page
├── districts/
│   ├── page.tsx               # District search
│   └── [id]/page.tsx          # District detail
├── anomalies/page.tsx         # Anomaly dashboard
├── query/page.tsx             # NLP query interface
└── components/
    ├── DistrictSearch.tsx     # Search & filter
    ├── FinanceChart.tsx       # Recharts visualizations
    ├── AnomalyList.tsx        # Flagged issues
    ├── NLPQuery.tsx           # Natural language input
    └── StatCard.tsx           # KPI display cards
```

#### ✅ Task 5.3: Implement Key Features
**Status**: PENDING

1. **District Search & Filter**
   - Search by name
   - Filter by enrollment size, spending range
   - Sort by various metrics

2. **Financial Visualizations**
   - Line charts: Spending trends over time
   - Bar charts: District comparisons
   - Scatter plots: Enrollment vs spending
   - Heatmaps: Anomaly detection

3. **NLP Query Interface**
   - Text input with autocomplete
   - Sample queries for guidance
   - Real-time results display
   - Export to CSV/PDF

4. **Anomaly Dashboard**
   - Filter by flag type
   - Year-over-year comparisons
   - Drill-down to district details

---

## 🚀 Phase 4: Deployment (Days 9-10)

### Production Deployment

#### ✅ Task 6.1: Deploy FastAPI Backend
**Status**: PENDING

**Option A: Railway**
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

**Option B: Render**
1. Connect GitHub repository
2. Create new Web Service
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
5. Add environment variables

**Environment Variables to Set**:
- `SUPABASE_DB_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `OPENAI_API_KEY`

#### ✅ Task 6.2: Deploy Next.js Frontend
**Status**: PENDING

**Vercel Deployment**:
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd texas-isd-portal
vercel --prod
```

**Environment Variables**:
- `NEXT_PUBLIC_API_URL` (Railway/Render backend URL)
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

#### ✅ Task 6.3: Configure CORS & Security
**Status**: PENDING

**Update API CORS settings**:
```python
# In src/api.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-vercel-app.vercel.app",
        "http://localhost:3000"  # Development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

---

## 📈 Phase 5: Optimization & Scaling (Ongoing)

### Performance Enhancements

#### ✅ Task 7.1: Database Optimization
- [ ] Add additional indexes for common queries
- [ ] Refresh materialized view `v_anomaly_flags` nightly
- [ ] Implement query result caching (Redis)
- [ ] Set up read replicas for high traffic

#### ✅ Task 7.2: API Improvements
- [ ] Implement rate limiting (10 req/min per IP)
- [ ] Add request/response compression
- [ ] Set up API key authentication for power users
- [ ] Create webhook notifications for new anomalies

#### ✅ Task 7.3: Frontend Enhancements
- [ ] Add skeleton loading states
- [ ] Implement infinite scroll for large datasets
- [ ] Create shareable report URLs
- [ ] Add PDF export functionality

---

## 🎯 Success Metrics

### Technical KPIs
- [ ] API response time < 500ms (p95)
- [ ] NLP query accuracy > 90%
- [ ] Database query performance < 100ms
- [ ] Frontend load time < 2s
- [ ] 99.9% uptime

### Business KPIs
- [ ] 1000+ districts accessible
- [ ] 17 years of financial data (2008-2024)
- [ ] 100+ anomalies detected
- [ ] Public transparency portal live
- [ ] Policy insights generated

---

## 🔧 Troubleshooting Guide

### Common Issues

**Issue 1: Database Connection Fails**
```bash
# Check connection string format
echo $SUPABASE_DB_URL
# Should be: postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
```

**Issue 2: NLP Queries Return Errors**
```bash
# Verify OpenAI API key
python -c "import openai; print(openai.api_key)"

# Test database views exist
psql $SUPABASE_DB_URL -c "\dv"
```

**Issue 3: Data Import Fails**
```bash
# Check CSV format
head -n 5 data/texas_finance_clean.csv

# Verify column count matches schema
wc -l data/texas_finance_clean.csv
```

---

## 📚 Resources

### Documentation
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [LangChain SQL Agent](https://python.langchain.com/docs/use_cases/sql/)
- [Supabase Docs](https://supabase.com/docs)
- [Next.js App Router](https://nextjs.org/docs/app)

### Sample Queries
1. "Which district has highest debt per student?"
2. "Show Austin ISD budget trend 2015-2020"
3. "Find districts with declining enrollment but increasing spending"
4. "Compare top 10 districts by total revenue"
5. "What's the statewide average spending per student by year?"

---

## 🎉 Next Steps

### Immediate Actions (Today)
1. ✅ Verify `.env` file configuration
2. ✅ Install Python dependencies
3. ✅ Run database schema creation
4. ✅ Import financial data to Supabase
5. ✅ Test NLP engine with sample queries

### This Week
- [ ] Complete API testing and validation
- [ ] Add Pydantic schema enforcement
- [ ] Create agent framework structure
- [ ] Begin frontend development

### Next Week
- [ ] Deploy backend to Railway/Render
- [ ] Deploy frontend to Vercel
- [ ] Configure production security
- [ ] Launch public transparency portal

---

**Last Updated**: 2025-10-06
**Project Status**: 🟡 Setup Phase
**Next Milestone**: Database Import & API Testing

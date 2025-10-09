"""
FastAPI service for Texas School Finance Data Portal
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
from dotenv import load_dotenv
import asyncpg
from datetime import datetime

from nlp_engine import TexasFinanceNLPEngine

load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Texas School Finance API",
    description="API for querying Texas ISD financial data with natural language",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize NLP engine
nlp_engine = TexasFinanceNLPEngine()

# Pydantic models
class NLPQueryRequest(BaseModel):
    question: str = Field(..., description="Natural language question about Texas school finances")

class NLPQueryResponse(BaseModel):
    success: bool
    question: str
    answer: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class DistrictSummary(BaseModel):
    district_number: str
    district_name: str
    year: int
    total_revenue: float
    total_spend: float
    enrollment: Optional[int]
    spend_per_student: Optional[float]
    revenue_per_student: Optional[float]

class AnomalyFlag(BaseModel):
    district_number: str
    district_name: str
    year: int
    revenue_drop_flag: bool
    spend_spike_flag: bool
    per_student_spike_flag: bool
    enrollment_decline_flag: bool

# Database connection pool
async def get_db_pool():
    """Create connection pool for direct queries"""
    return await asyncpg.create_pool(
        os.getenv("SUPABASE_DB_URL"),
        min_size=1,
        max_size=10
    )

# Initialize pool on startup
@app.on_event("startup")
async def startup():
    app.state.db_pool = await get_db_pool()

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

# API Endpoints

@app.get("/", tags=["General"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Texas School Finance API",
        "documentation": "/docs",
        "endpoints": {
            "nlp_query": "/query",
            "districts": "/districts",
            "district_summary": "/district/{district_number}/summary",
            "anomalies": "/anomalies",
            "sample_queries": "/sample-queries"
        }
    }

@app.post("/query", response_model=NLPQueryResponse, tags=["NLP"])
async def nlp_query(request: NLPQueryRequest):
    """
    Process natural language query about Texas school finances
    
    Example queries:
    - "Show Dallas ISD spending per student 2020-2024"
    - "Which districts have declining enrollment?"
    - "Compare Austin ISD and Houston ISD budgets"
    """
    result = nlp_engine.query(request.question)
    return NLPQueryResponse(**result)

@app.get("/districts", tags=["Districts"])
async def list_districts(
    search: Optional[str] = Query(None, description="Search districts by name"),
    limit: int = Query(100, ge=1, le=500)
):
    """List all districts with optional search"""
    async with app.state.db_pool.acquire() as conn:
        if search:
            query = """
                SELECT DISTINCT district_number, district_name 
                FROM v_finance_summary 
                WHERE district_name ILIKE $1
                ORDER BY district_name 
                LIMIT $2
            """
            rows = await conn.fetch(query, f"%{search}%", limit)
        else:
            query = """
                SELECT DISTINCT district_number, district_name 
                FROM v_finance_summary 
                ORDER BY district_name 
                LIMIT $1
            """
            rows = await conn.fetch(query, limit)
        
        return [dict(row) for row in rows]

@app.get("/district/{district_number}/summary", tags=["Districts"])
async def get_district_summary(
    district_number: str,
    start_year: Optional[int] = Query(None, ge=2008, le=2024),
    end_year: Optional[int] = Query(None, ge=2008, le=2024)
):
    """Get financial summary for a specific district"""
    async with app.state.db_pool.acquire() as conn:
        query = """
            SELECT * FROM v_finance_summary 
            WHERE district_number = $1
        """
        params = [district_number]
        
        if start_year and end_year:
            query += " AND year BETWEEN $2 AND $3"
            params.extend([start_year, end_year])
        elif start_year:
            query += " AND year >= $2"
            params.append(start_year)
        elif end_year:
            query += " AND year <= $2"
            params.append(end_year)
            
        query += " ORDER BY year"
        
        rows = await conn.fetch(query, *params)
        
        if not rows:
            raise HTTPException(status_code=404, detail="District not found")
        
        return [dict(row) for row in rows]

@app.get("/anomalies", tags=["Anomalies"])
async def get_anomalies(
    year: Optional[int] = Query(None, ge=2008, le=2024),
    flag_type: Optional[str] = Query(
        None, 
        description="Filter by flag type",
        enum=["revenue_drop", "spend_spike", "per_student_spike", "enrollment_decline"]
    ),
    limit: int = Query(100, ge=1, le=500)
):
    """Get districts with anomaly flags"""
    async with app.state.db_pool.acquire() as conn:
        query = "SELECT * FROM v_anomaly_flags WHERE "
        conditions = []
        params = []
        param_count = 0
        
        # Build dynamic WHERE clause
        if year:
            param_count += 1
            conditions.append(f"year = ${param_count}")
            params.append(year)
        
        if flag_type:
            param_count += 1
            flag_column = f"{flag_type}_flag"
            conditions.append(f"{flag_column} = ${param_count}")
            params.append(True)
        
        # If no conditions, get all anomalies
        if not conditions:
            conditions.append("(revenue_drop_flag OR spend_spike_flag OR per_student_spike_flag OR enrollment_decline_flag)")
        
        query += " AND ".join(conditions)
        query += f" ORDER BY year DESC, district_name LIMIT ${param_count + 1}"
        params.append(limit)
        
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]

@app.get("/sample-queries", tags=["NLP"])
async def get_sample_queries():
    """Get sample natural language queries"""
    return {
        "sample_queries": nlp_engine.get_sample_queries(),
        "usage": "POST these questions to /query endpoint"
    }

@app.get("/stats", tags=["General"])
async def get_stats():
    """Get database statistics"""
    async with app.state.db_pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(DISTINCT district_number) as total_districts,
                COUNT(DISTINCT year) as total_years,
                MIN(year) as start_year,
                MAX(year) as end_year,
                COUNT(*) as total_records,
                ROUND(AVG(spend_per_student)::numeric, 2) as avg_spend_per_student
            FROM v_finance_summary
        """)
        
        return dict(stats)

@app.get("/health", tags=["General"])
async def health_check():
    """Health check endpoint"""
    try:
        async with app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# Run with: uvicorn src.api:app --reload --port 8000

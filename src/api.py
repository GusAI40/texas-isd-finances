"""
FastAPI service for Texas School Finance Data Portal
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .sample_queries import SAMPLE_QUERIES

load_dotenv()

# Data coverage (TEA summarized financial data). Override via env if a new
# release extends the range.
MIN_YEAR = int(os.getenv("DATA_MIN_YEAR", "2008"))
MAX_YEAR = int(os.getenv("DATA_MAX_YEAR", "2024"))

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the database pool on startup, close it on shutdown.

    The app still boots when SUPABASE_DB_URL is unset so the portal page,
    /docs and /health remain reachable; data endpoints return 503 until the
    database is configured.
    """
    app.state.db_pool = None
    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url:
        try:
            app.state.db_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
        except Exception as exc:  # pragma: no cover - depends on environment
            print(f"WARNING: could not connect to database: {exc}")
    else:
        print("WARNING: SUPABASE_DB_URL not set - data endpoints will return 503")
    yield
    if app.state.db_pool is not None:
        await app.state.db_pool.close()


app = FastAPI(
    title="Texas School Finance API",
    description=(
        "Public API for querying Texas ISD financial data "
        f"({MIN_YEAR}-{MAX_YEAR}) with natural language support"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: this is a public, read-only API. With a wildcard origin, credentials
# must be disabled (browsers reject the combination anyway). Set
# CORS_ALLOW_ORIGINS to a comma-separated list to restrict origins.
_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# The NLP engine needs an OpenAI key and a database connection, so it is
# created lazily on first use rather than at import time.
_nlp_engine = None


def get_nlp_engine():
    global _nlp_engine
    if _nlp_engine is None:
        from .nlp_engine import TexasFinanceNLPEngine

        _nlp_engine = TexasFinanceNLPEngine()
    return _nlp_engine


def get_pool(request: Request):
    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set SUPABASE_DB_URL and restart.",
        )
    return pool


# Pydantic models
class NLPQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500,
                          description="Natural language question about Texas school finances")


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


# API Endpoints

@app.get("/", include_in_schema=False)
async def portal():
    """Serve the public portal page."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Texas School Finance API", "documentation": "/docs"}


@app.get("/api", tags=["General"])
async def api_info():
    """API information and endpoint directory"""
    return {
        "message": "Texas School Finance API",
        "data_coverage": f"{MIN_YEAR}-{MAX_YEAR}",
        "documentation": "/docs",
        "endpoints": {
            "nlp_query": "POST /query",
            "districts": "GET /districts",
            "district_summary": "GET /district/{district_number}/summary",
            "anomalies": "GET /anomalies",
            "sample_queries": "GET /sample-queries",
            "stats": "GET /stats",
            "health": "GET /health",
        },
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
    try:
        engine = get_nlp_engine()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="NLP engine not configured. Set OPENAI_API_KEY and SUPABASE_DB_URL.",
        )
    result = engine.query(request.question)
    return NLPQueryResponse(**result)


@app.get("/districts", tags=["Districts"])
async def list_districts(
    request: Request,
    search: Optional[str] = Query(None, max_length=100, description="Search districts by name"),
    limit: int = Query(100, ge=1, le=500),
):
    """List all districts with optional search"""
    pool = get_pool(request)
    async with pool.acquire() as conn:
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
    request: Request,
    district_number: str,
    start_year: Optional[int] = Query(None, ge=MIN_YEAR, le=MAX_YEAR),
    end_year: Optional[int] = Query(None, ge=MIN_YEAR, le=MAX_YEAR),
):
    """Get financial summary for a specific district"""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        query = """
            SELECT * FROM v_finance_summary
            WHERE district_number = $1
        """
        params: List[Any] = [district_number]

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


# Whitelist mapping of API flag names to view columns. Never interpolate
# user input into SQL outside of this mapping.
_FLAG_COLUMNS = {
    "revenue_drop": "revenue_drop_flag",
    "spend_spike": "spend_spike_flag",
    "per_student_spike": "per_student_spike_flag",
    "enrollment_decline": "enrollment_decline_flag",
}


@app.get("/anomalies", tags=["Anomalies"])
async def get_anomalies(
    request: Request,
    year: Optional[int] = Query(None, ge=MIN_YEAR, le=MAX_YEAR),
    flag_type: Optional[str] = Query(
        None,
        description="Filter by flag type",
        enum=list(_FLAG_COLUMNS.keys()),
    ),
    limit: int = Query(100, ge=1, le=500),
):
    """Get districts with anomaly flags"""
    if flag_type is not None and flag_type not in _FLAG_COLUMNS:
        raise HTTPException(status_code=422, detail="Invalid flag_type")

    pool = get_pool(request)
    async with pool.acquire() as conn:
        conditions: List[str] = []
        params: List[Any] = []

        if year:
            params.append(year)
            conditions.append(f"year = ${len(params)}")

        if flag_type:
            params.append(True)
            conditions.append(f"{_FLAG_COLUMNS[flag_type]} = ${len(params)}")

        if not conditions:
            conditions.append(
                "(revenue_drop_flag OR spend_spike_flag OR per_student_spike_flag OR enrollment_decline_flag)"
            )

        params.append(limit)
        query = (
            "SELECT * FROM v_anomaly_flags WHERE "
            + " AND ".join(conditions)
            + f" ORDER BY year DESC, district_name LIMIT ${len(params)}"
        )

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


@app.get("/sample-queries", tags=["NLP"])
async def get_sample_queries():
    """Get sample natural language queries"""
    return {
        "sample_queries": SAMPLE_QUERIES,
        "usage": "POST these questions to /query endpoint",
    }


@app.get("/stats", tags=["General"])
async def get_stats(request: Request):
    """Get database statistics"""
    pool = get_pool(request)
    async with pool.acquire() as conn:
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
async def health_check(request: Request):
    """Health check endpoint"""
    pool = request.app.state.db_pool
    if pool is None:
        return {"status": "degraded", "database": "not configured"}
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# Run with: uvicorn src.api:app --reload --port 8000

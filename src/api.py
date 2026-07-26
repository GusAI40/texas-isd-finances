"""
FastAPI service for Texas School Finance Data Portal
"""
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .sample_queries import SAMPLE_QUERIES

load_dotenv()

# Data coverage (TEA summarized financial data, fiscal years). Override via
# env if a new release extends the range.
MIN_YEAR = int(os.getenv("DATA_MIN_YEAR", "2009"))
MAX_YEAR = int(os.getenv("DATA_MAX_YEAR", "2025"))

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
            # statement_cache_size=0 keeps asyncpg compatible with Supabase's
            # transaction pooler (PgBouncer-style), the recommended mode for
            # serverless deploys; harmless on direct/session connections.
            app.state.db_pool = await asyncpg.create_pool(
                db_url, min_size=1, max_size=10, statement_cache_size=0
            )
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
            "district_dollar": "GET /district/{district_number}/dollar",
            "district_outcomes": "GET /district/{district_number}/outcomes",
            "anomalies": "GET /anomalies",
            "sample_queries": "GET /sample-queries",
            "stats": "GET /stats",
            "health": "GET /health",
        },
    }


# Simple sliding-window rate limit for /query: each call costs a paid
# OpenAI request. Per-process state — on serverless each warm instance
# enforces its own window, which still bounds abuse per instance; put a
# CDN/WAF limit in front for a hard global guarantee.
_RATE_LIMIT = int(os.getenv("QUERY_RATE_LIMIT", "10"))  # requests
_RATE_WINDOW = 60.0  # seconds
_rate_buckets: Dict[str, List[float]] = {}


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    bucket = [t for t in _rate_buckets.get(ip, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        _rate_buckets[ip] = bucket
        return True
    bucket.append(now)
    _rate_buckets[ip] = bucket
    if len(_rate_buckets) > 10000:  # bound memory
        _rate_buckets.clear()
    return False


@app.post("/query", response_model=NLPQueryResponse, tags=["NLP"])
async def nlp_query(request: NLPQueryRequest, http_request: Request):
    """
    Process natural language query about Texas school finances

    Example queries:
    - "Show Dallas ISD spending per student 2020-2024"
    - "Which districts have declining enrollment?"
    - "Compare Austin ISD and Houston ISD budgets"
    """
    client_ip = (http_request.headers.get("x-forwarded-for", "") or "").split(",")[0].strip() \
        or (http_request.client.host if http_request.client else "unknown")
    if _rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {_RATE_LIMIT} questions per minute. Please wait a moment.",
        )
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
    district_number: Optional[str] = Query(None, max_length=6, description="Filter to one district"),
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

        if district_number:
            params.append(district_number)
            conditions.append(f"district_number = ${len(params)}")

        if flag_type:
            params.append(True)
            conditions.append(f"{_FLAG_COLUMNS[flag_type]} = ${len(params)}")
        else:
            # /anomalies must only ever return flagged rows; without a
            # specific flag filter, require at least one flag to be set
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


@app.get("/benchmarks", tags=["Benchmarks"])
async def get_benchmarks(request: Request):
    """Statewide per-year medians — the 'what's normal?' context that
    district numbers are meaningless without."""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT year,
                   COUNT(*) AS n_districts,
                   ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY spend_per_student))::numeric, 0)
                       AS median_spend_per_student,
                   ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY revenue_per_student))::numeric, 0)
                       AS median_revenue_per_student,
                   SUM(enrollment) AS total_enrollment
            FROM v_finance_summary
            WHERE spend_per_student IS NOT NULL AND spend_per_student > 0
            GROUP BY year ORDER BY year
        """)
        return [dict(r) for r in rows]


@app.get("/district/{district_number}/peers", tags=["Districts"])
async def get_district_peers(request: Request, district_number: str):
    """Peer comparison, plus this district's statewide percentile. The #1
    demand in admin usage simulation (docs/UX_RESEARCH.md).

    Peers come from the precomputed similarity graph (k-NN on EXOGENOUS
    features only — size, enrollment trajectory, funding capacity, local-tax
    share — so benchmarking spending against them is not circular; see
    scripts/build_similarity_graph.py). Falls back to an enrollment window
    if the graph has no edges for this district."""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        me = await conn.fetchrow("""
            SELECT * FROM v_finance_summary
            WHERE district_number = $1 AND enrollment > 0 AND spend_per_student IS NOT NULL
            ORDER BY year DESC LIMIT 1
        """, district_number)
        if me is None:
            raise HTTPException(status_code=404, detail="District not found or has no usable data")

        basis = "similarity_graph"
        peers = await conn.fetch("""
            SELECT f.district_number, f.district_name, f.enrollment, f.spend_per_student,
                   f.revenue_per_student, f.instruction_spend, f.total_spend
            FROM district_similarity s
            JOIN v_finance_summary f
              ON f.district_number = s.peer_number AND f.year = $2
            WHERE s.district_number = $1
              AND f.spend_per_student IS NOT NULL AND f.spend_per_student > 0
            ORDER BY s.rank LIMIT 12
        """, district_number, me["year"])

        if not peers:
            basis = "enrollment_window"
            peers = await conn.fetch("""
                SELECT district_number, district_name, enrollment, spend_per_student,
                       revenue_per_student, instruction_spend, total_spend
                FROM v_finance_summary
                WHERE year = $1 AND district_number != $2
                  AND enrollment BETWEEN $3 * 0.5 AND $3 * 2
                  AND spend_per_student IS NOT NULL AND spend_per_student > 0
                ORDER BY ABS(enrollment - $3) LIMIT 12
            """, me["year"], district_number, me["enrollment"])

        pct = await conn.fetchrow("""
            SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE spend_per_student < $1) / COUNT(*), 0)
                       AS spend_percentile,
                   ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY spend_per_student))::numeric, 0)
                       AS statewide_median_spend
            FROM v_finance_summary
            WHERE year = $2 AND spend_per_student IS NOT NULL AND spend_per_student > 0
        """, me["spend_per_student"], me["year"])

        return {
            "district": dict(me),
            "peers": [dict(p) for p in peers],
            "statewide": dict(pct),
            "basis": basis,
        }


@app.get("/district/{district_number}/breakdown", tags=["Districts"])
async def get_district_breakdown(request: Request, district_number: str):
    """Function-level spending breakdown (MECE categories from TEA function
    codes) for every year — where the money actually goes."""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM v_spending_breakdown
            WHERE district_number = $1 AND total_operating > 0
            ORDER BY year
        """, district_number)
        if not rows:
            raise HTTPException(status_code=404, detail="District not found")
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# The dollar: one district's spending as 100 pennies, with the same 100
# pennies for its structural peers and for Texas as a whole. Computed here,
# not in the browser, so the portal, the share card and any future client all
# tell the same story from one definition.
#
# Each entry: (key, label, source columns, plain-English contents, TEA codes).
# ---------------------------------------------------------------------------
_DOLLAR_CATEGORIES = [
    ("classroom", "Classroom teaching", ("classroom_instruction",),
     "Teachers' pay and benefits, classroom materials, school libraries and media "
     "specialists, and training for teachers.", "TEA functions 11, 12, 13"),
    ("debt", "Debt payments", ("debt_service",),
     "Principal and interest on bonds voters approved in past elections — mostly for "
     "buildings that are already standing.", "TEA object 6500"),
    ("construction", "Construction", ("capital_projects",),
     "New buildings, major renovations, land, and large equipment purchases.",
     "TEA object 6600"),
    ("admin", "Principals & administration", ("leadership_admin",),
     "Principals and assistant principals, campus front offices, the superintendent's "
     "office, and central business functions.", "TEA functions 21, 23, 41, 92"),
    ("facilities", "Buildings & upkeep", ("facilities_maintenance",),
     "Custodians, electricity and water, groundskeeping, and the repairs that keep "
     "buildings open.", "TEA function 51"),
    ("transport_food", "Buses & meals", ("transportation", "food_service"),
     "School buses, routes and drivers, plus cafeterias and the food served in them.",
     "TEA functions 34, 35"),
    ("support", "Counselors, nurses & support", ("student_support",),
     "Counselors, social workers, and school nurses.", "TEA functions 31, 32, 33"),
    ("extracurricular", "Sports & activities", ("extracurricular",),
     "Athletics, band, UIL academics, clubs, and other activities outside class time.",
     "TEA function 36"),
    ("safety_tech", "Safety & technology", ("safety_technology",),
     "Campus security and policing, plus the district's computers, networks, and data "
     "systems. (Technology cannot be separated from security in this dataset.)",
     "TEA functions 52, 53"),
    ("community", "Community services", ("community_services",),
     "Programs the district runs for the wider community, such as adult education and "
     "parent outreach.", "TEA function 61"),
]
_COLUMN_LABELS = {
    "transportation": "School buses",
    "food_service": "Cafeterias & food",
}
_OTHER = ("other", "Everything else",
          "Everything the function codes above do not capture — including transfers "
          "between funds and smaller categories TEA does not break out separately.",
          "residual: total spending minus the categories above")


def _cat_amounts(row) -> Dict[str, float]:
    """Category dollar amounts for one breakdown row."""
    return {k: sum(float(row[c] or 0) for c in cols)
            for k, _lbl, cols, _desc, _codes in _DOLLAR_CATEGORIES}


def _to_pennies(shares: Dict[str, float]) -> Dict[str, int]:
    """Fractional shares (summing to <=1) → integer cents summing to exactly 100,
    using the largest-remainder method so no penny is invented or lost."""
    keys = list(shares)
    exact = [100.0 * shares[k] for k in keys]
    cents = [int(e) for e in exact]
    left = 100 - sum(cents)
    order = sorted(range(len(keys)), key=lambda i: -(exact[i] - int(exact[i])))
    for i in range(max(0, left)):
        cents[order[i % len(order)]] += 1
    return dict(zip(keys, cents))


def _dollar_shares(row) -> Optional[Dict[str, float]]:
    """One district's spending as fractional shares of its total, incl. residual."""
    total = float(row["total_spend"] or 0)
    if total <= 0:
        return None
    amts = _cat_amounts(row)
    named = sum(amts.values())
    if named > total * 1.02:  # categories exceed the stated total → unusable row
        return None
    shares = {k: v / total for k, v in amts.items()}
    shares[_OTHER[0]] = max(0.0, (total - named) / total)
    return shares


@app.get("/dollar/texas", tags=["General"])
async def get_texas_dollar(request: Request):
    """The whole state's dollar, pooled: every category summed across every
    district and divided by total spending. Unlike the per-district peer bars
    this needs no rescaling — it is one real dollar made of real dollars."""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        year = await conn.fetchval("SELECT MAX(year) FROM v_spending_breakdown")
        cols = sorted({c for _k, _l, cc, _d, _co in _DOLLAR_CATEGORIES for c in cc})
        sums = ", ".join(f"SUM(COALESCE(b.{c},0)) AS {c}" for c in cols)
        row = await conn.fetchrow(f"""
            SELECT {sums}, SUM(f.total_spend) AS total_spend,
                   SUM(f.enrollment) AS enrollment, COUNT(*) AS districts
            FROM v_spending_breakdown b
            JOIN v_finance_summary f ON f.district_number = b.district_number AND f.year = b.year
            WHERE b.year = $1 AND f.enrollment > 0 AND f.total_spend > 0
        """, year)
        shares = _dollar_shares(row)
        if shares is None:
            raise HTTPException(status_code=503, detail="Statewide totals unavailable")
        cents = _to_pennies(shares)
        amounts = _cat_amounts(row)
        total = float(row["total_spend"])
        amounts[_OTHER[0]] = max(0.0, total - sum(amounts.values()))
        labels = {k: (lbl, desc, codes) for k, lbl, _c, desc, codes in _DOLLAR_CATEGORIES}
        labels[_OTHER[0]] = (_OTHER[1], _OTHER[2], _OTHER[3])
        parts = [{"key": k, "label": labels[k][0], "contents": labels[k][1],
                  "codes": labels[k][2], "cents": cents[k], "amount": round(amounts[k])}
                 for k in shares]
        parts.sort(key=lambda p: (p["key"] == _OTHER[0], -p["cents"]))
        return {"year": year, "districts": row["districts"], "students": row["enrollment"],
                "total_spend": round(total), "per_student": round(total / float(row["enrollment"])),
                "parts": parts}


@app.get("/district/{district_number}/dollar", tags=["Districts"])
async def get_district_dollar(request: Request, district_number: str):
    """Where one dollar goes, as 100 pennies — for this district, for its
    structural peers, and for Texas as a whole, with the dollar amount at stake
    in each category if the district spent at the peer rate.

    Peer shares are the MEDIAN share across peer districts, renormalised to 100
    pennies (medians of separate categories do not sum to a whole dollar on
    their own). Dollars at stake use median dollars *per student*, so they are
    real money, not renormalised."""
    import statistics

    pool = get_pool(request)
    async with pool.acquire() as conn:
        year = await conn.fetchval("""
            SELECT MAX(b.year) FROM v_spending_breakdown b
            JOIN v_finance_summary f ON f.district_number = b.district_number AND f.year = b.year
            WHERE b.district_number = $1 AND f.enrollment > 0 AND f.total_spend > 0
        """, district_number)
        if year is None:
            raise HTTPException(status_code=404, detail="District not found or has no usable data")

        rows = await conn.fetch("""
            SELECT b.*, f.enrollment, f.total_spend,
                   EXISTS (SELECT 1 FROM district_similarity s
                           WHERE s.district_number = $1 AND s.peer_number = b.district_number)
                       AS is_peer
            FROM v_spending_breakdown b
            JOIN v_finance_summary f ON f.district_number = b.district_number AND f.year = b.year
            WHERE b.year = $2 AND f.enrollment > 0 AND f.total_spend > 0
        """, district_number, year)

        me = next((r for r in rows if r["district_number"] == district_number), None)
        my_shares = _dollar_shares(me) if me is not None else None
        if my_shares is None:
            raise HTTPException(status_code=404, detail="District not found or has no usable data")

        prev = await conn.fetchrow("""
            SELECT b.*, f.total_spend FROM v_spending_breakdown b
            JOIN v_finance_summary f ON f.district_number = b.district_number AND f.year = b.year
            WHERE b.district_number = $1 AND b.year = $2 AND f.total_spend > 0
        """, district_number, year - 5)
        prev_shares = _dollar_shares(prev) if prev is not None else None

        enroll = float(me["enrollment"])
        total = float(me["total_spend"])
        peers = [r for r in rows if r["is_peer"] and r["district_number"] != district_number]

        def cohort_stats(cohort):
            """(median share per category, median dollars per student per category)."""
            shares, per_student = {}, {}
            parsed = [(_dollar_shares(r), r) for r in cohort]
            parsed = [(s, r) for s, r in parsed if s]
            if len(parsed) < 4:
                return None, None
            keys = list(my_shares)
            for k in keys:
                shares[k] = statistics.median(s[k] for s, _ in parsed)
            for k, _lbl, cols, _d, _c in _DOLLAR_CATEGORIES:
                per_student[k] = statistics.median(
                    sum(float(r[c] or 0) for c in cols) / float(r["enrollment"]) for _, r in parsed)
            tot = sum(shares.values()) or 1.0
            return _to_pennies({k: v / tot for k, v in shares.items()}), per_student

        peer_cents, peer_ps = cohort_stats(peers)
        state_cents, state_ps = cohort_stats(rows)

        my_cents = _to_pennies(my_shares)
        prev_cents = _to_pennies(prev_shares) if prev_shares else None
        labels = {k: (lbl, desc, codes) for k, lbl, _c, desc, codes in _DOLLAR_CATEGORIES}
        labels[_OTHER[0]] = (_OTHER[1], _OTHER[2], _OTHER[3])
        columns = {k: list(cols) for k, _l, cols, _d, _c in _DOLLAR_CATEGORIES}
        columns[_OTHER[0]] = []
        amounts = _cat_amounts(me)
        amounts[_OTHER[0]] = max(0.0, total - sum(amounts.values()))

        parts = []
        for key in my_shares:
            lbl, desc, codes = labels[key]
            mine_ps = amounts[key] / enroll
            ppl = (peer_ps or {}).get(key)
            cols = columns[key]
            parts.append({
                "key": key,
                "label": lbl,
                "contents": desc,
                "codes": codes,
                "columns": cols,
                "components": [{"label": _COLUMN_LABELS.get(c, c),
                                "amount": round(float(me[c] or 0))} for c in cols]
                              if len(cols) > 1 else [],
                "amount": round(amounts[key]),
                "per_student": round(mine_ps),
                "cents": my_cents[key],
                "cents_prev": prev_cents[key] if prev_cents else None,
                "peer_cents": (peer_cents or {}).get(key),
                "state_cents": (state_cents or {}).get(key),
                "peer_per_student": round(ppl) if ppl is not None else None,
                "state_per_student": (round((state_ps or {}).get(key))
                                      if (state_ps or {}).get(key) is not None else None),
                "dollars_vs_peers": round((mine_ps - ppl) * enroll) if ppl is not None else None,
            })
        parts.sort(key=lambda p: (p["key"] == _OTHER[0], -p["cents"]))

        return {
            "district_number": district_number,
            "district_name": me["district_name"],
            "year": year,
            "prev_year": (year - 5) if prev_cents else None,
            "enrollment": me["enrollment"],
            "total_spend": round(total),
            "per_student": round(total / enroll),
            "peer_count": len(peers),
            "state_count": len(rows),
            "parts": parts,
        }


def _runs(rows, pred):
    """Consecutive runs of rows satisfying pred → list of (start_year, end_year)."""
    runs, start, prev = [], None, None
    for r in rows:
        if pred(r):
            if start is None:
                start = r["year"]
            prev = r["year"]
        else:
            if start is not None:
                runs.append((start, prev))
                start = None
    if start is not None:
        runs.append((start, prev))
    return runs


@app.get("/district/{district_number}/turnarounds", tags=["Districts"])
async def get_district_turnarounds(request: Request, district_number: str):
    """Walk the similarity graph and find structural peers that reversed a
    sustained deficit (>=2 deficit years then >=2 surplus years) or a
    sustained enrollment decline (>=3 down years then >=2 up years).
    See docs/GRAPH_INSIGHTS.md."""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        peers = await conn.fetch("""
            SELECT s.peer_number, f.district_name, f.year, f.total_revenue,
                   f.total_spend, f.enrollment
            FROM district_similarity s
            JOIN v_finance_summary f ON f.district_number = s.peer_number
            WHERE s.district_number = $1
              AND f.total_revenue IS NOT NULL AND f.total_spend IS NOT NULL
            ORDER BY s.peer_number, f.year
        """, district_number)
        if not peers:
            return {"turnarounds": [], "peers_scanned": 0}

        by_peer: Dict[str, List[Any]] = {}
        names: Dict[str, str] = {}
        for r in peers:
            by_peer.setdefault(r["peer_number"], []).append(r)
            names[r["peer_number"]] = r["district_name"]

        results = []
        for pid, rows in by_peer.items():
            deficits = _runs(rows, lambda r: r["total_spend"] > r["total_revenue"])
            latest_year = rows[-1]["year"]
            for (d0, d1) in deficits:
                if d1 - d0 + 1 >= 2 and d1 < latest_year - 1:
                    after = [r for r in rows if r["year"] > d1]
                    if len(after) >= 2 and all(
                            r["total_spend"] <= r["total_revenue"] for r in after[:2]):
                        results.append({
                            "district_number": pid, "district_name": names[pid],
                            "type": "deficit_reversal",
                            "struggled": f"{d0}-{d1}",
                            "recovered_since": d1 + 1,
                        })
                        break
            enr = [r for r in rows if r["enrollment"]]
            declines = _runs(
                [{"year": b["year"], "down": b["enrollment"] < a["enrollment"]}
                 for a, b in zip(enr, enr[1:])],
                lambda r: r["down"])
            for (d0, d1) in declines:
                if d1 - d0 + 1 >= 3 and d1 < latest_year - 1:
                    after = [b for a, b in zip(enr, enr[1:]) if b["year"] > d1]
                    if len(after) >= 2:
                        pairs = [b for b in after[:2]]
                        idx0 = next(i for i, r in enumerate(enr) if r["year"] == pairs[0]["year"])
                        if all(enr[idx0 + k]["enrollment"] > enr[idx0 + k - 1]["enrollment"]
                               for k in range(len(pairs))):
                            results.append({
                                "district_number": pid, "district_name": names[pid],
                                "type": "enrollment_reversal",
                                "struggled": f"{d0}-{d1}",
                                "recovered_since": d1 + 1,
                            })
                            break
        return {"turnarounds": results, "peers_scanned": len(by_peer)}


# Actionable-intelligence metric definitions. Each is compared against the
# district's SIMILARITY-GRAPH peers (apples-to-apples), expressed in dollars.
# kind "per_student": value = num/enrollment, impact = (value-peer_med)*enroll
# kind "share": value = num/base, impact = (value-peer_med)*base
_INSIGHT_METRICS = [
    {"key": "operating", "label": "Operating spending", "kind": "per_student",
     "num": "total_operating", "unit": "per student",
     "high": "Higher total operating cost per student than peers — worth confirming what it buys.",
     "low": "Leaner operating cost per student than peers."},
    {"key": "instruction", "label": "Classroom instruction", "kind": "share",
     "num": "classroom_instruction", "base": "total_operating",
     "high": "A larger share reaches classrooms than peers — a strength.",
     "low": "A smaller share reaches classrooms than peers — worth asking where the rest goes."},
    {"key": "admin", "label": "Leadership & administration", "kind": "per_student",
     "num": "leadership_admin", "unit": "per student",
     "high": "Administrative overhead per student runs above peers — a common review target.",
     "low": "Administrative overhead per student runs below peers."},
    {"key": "facilities", "label": "Facilities & maintenance", "kind": "per_student",
     "num": "facilities_maintenance", "unit": "per student",
     "high": "Facilities cost per student is above peers — could be older buildings or an efficiency gap.",
     "low": "Facilities & maintenance cost per student is below peers."},
    {"key": "debt", "label": "Debt service", "kind": "per_student",
     "num": "debt_service", "unit": "per student",
     "high": "Debt payments per student are heavier than peers — check the bond schedule.",
     "low": "Debt payments per student are lighter than peers."},
    {"key": "payroll", "label": "Payroll share of operating", "kind": "share",
     "num": "obj_payroll", "base": "obj_total",
     "high": "A higher share goes to payroll than peers — less flexible budget.",
     "low": "A lower share goes to payroll than peers — more spent on outside services/supplies."},
    {"key": "contracted", "label": "Contracted (outsourced) services", "kind": "share",
     "num": "obj_contracted", "base": "obj_total",
     "high": "More is outsourced to contractors than peers — a procurement review target.",
     "low": "Less is outsourced than peers."},
]


@app.get("/district/{district_number}/insights", tags=["Districts"])
async def get_district_insights(request: Request, district_number: str):
    """Actionable intelligence: where this district materially differs from
    its similarity-graph peers, each finding quantified in dollars and ranked
    by magnitude. Peers come from the exogenous k-NN graph so the comparison
    is apples-to-apples."""
    import statistics

    pool = get_pool(request)
    async with pool.acquire() as conn:
        year = await conn.fetchval(
            "SELECT MAX(year) FROM v_finance_summary WHERE district_number = $1", district_number)
        if year is None:
            raise HTTPException(status_code=404, detail="District not found")

        rows = await conn.fetch("""
            WITH cohort AS (
                SELECT $1::text AS d, 0 AS peer
                UNION ALL
                SELECT peer_number, 1 FROM district_similarity WHERE district_number = $1
            )
            SELECT f.district_number, f.district_name, f.enrollment, c.peer,
                   f.spend_per_student, f.total_revenue, f.total_spend,
                   b.total_operating, b.classroom_instruction, b.leadership_admin,
                   b.facilities_maintenance, b.debt_service,
                   d.obj_payroll, d.obj_contracted, d.obj_total
            FROM cohort c
            JOIN v_finance_summary f ON f.district_number = c.d AND f.year = $2
            LEFT JOIN v_spending_breakdown b ON b.district_number = c.d AND b.year = $2
            LEFT JOIN v_spending_detail d ON d.district_number = c.d AND d.year = $2
            WHERE f.enrollment > 0
        """, district_number, year)

        me = next((dict(r) for r in rows if r["peer"] == 0), None)
        peers = [dict(r) for r in rows if r["peer"] == 1]
        if me is None or len(peers) < 4:
            return {"year": year, "peer_count": len(peers), "insights": [],
                    "note": "Not enough comparable peers for benchmarking."}

        enroll = me["enrollment"]

        def value_of(row, m):
            num = row.get(m["num"])
            if num is None:
                return None
            if m["kind"] == "per_student":
                e = row.get("enrollment")
                return num / e if e else None
            base = row.get(m["base"])
            return num / base if base else None

        insights = []
        for m in _INSIGHT_METRICS:
            mine = value_of(me, m)
            pvals = [v for v in (value_of(p, m) for p in peers) if v is not None]
            if mine is None or len(pvals) < 4:
                continue
            pmed = statistics.median(pvals)
            if pmed <= 0:
                continue
            dev = (mine - pmed) / pmed
            if abs(dev) < 0.20:  # materiality: within 20% of peers → not notable
                continue
            if m["kind"] == "per_student":
                impact = (mine - pmed) * enroll
            else:
                impact = (mine - pmed) * (me.get(m["base"]) or 0)
            if abs(impact) < 100000:  # dollar materiality floor
                continue
            direction = "above" if dev > 0 else "below"
            insights.append({
                "metric": m["label"],
                "your_value": round(mine, 2),
                "peer_median": round(pmed, 2),
                "unit": m.get("unit", "share of operating"),
                "pct_vs_peers": round(dev * 100, 0),
                "direction": direction,
                "dollar_impact": round(impact),
                "annual_dollars_vs_peers":
                    f"${abs(round(impact)):,}/year {'above' if impact > 0 else 'below'} peers",
                "finding": m["high"] if dev > 0 else m["low"],
            })

        insights.sort(key=lambda x: -abs(x["dollar_impact"]))
        total_swing = sum(i["dollar_impact"] for i in insights if i["metric"] != "Classroom instruction")
        return {
            "district_number": district_number,
            "district_name": me["district_name"],
            "year": year,
            "peer_count": len(peers),
            "enrollment": enroll,
            "net_variance_vs_peers": round(total_swing),
            "insights": insights[:6],
        }


@app.get("/district/{district_number}/spending-detail", tags=["Districts"])
async def get_district_spending_detail(request: Request, district_number: str):
    """Two more spending dimensions the summarized data already carries:
    OBJECT (what was bought — payroll/contracted/supplies/other, sums to
    operating) and PROGRAM (who it served — regular/special-ed/bilingual/
    career-tech/gifted/compensatory/athletics), every year."""
    pool = get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM v_spending_detail
            WHERE district_number = $1 AND obj_total > 0
            ORDER BY year
        """, district_number)
        if not rows:
            raise HTTPException(status_code=404, detail="District not found")
        return [dict(r) for r in rows]


# Loaded once per warm instance and sliced per request — the file is ~700 KB
# and identical between annual TEA releases, so re-reading it per call would
# be pure waste, and shipping the whole thing to the browser worse still.
_outcomes_cache: Optional[Dict[str, Any]] = None


def _outcomes() -> Optional[Dict[str, Any]]:
    global _outcomes_cache
    if _outcomes_cache is None:
        path = STATIC_DIR / "outcomes_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _outcomes_cache = json.load(fh)
    return _outcomes_cache


@app.get("/district/{district_number}/outcomes", tags=["Districts"])
async def get_district_outcomes(district_number: str):
    """What the money buys: student population, teaching workforce, and
    results, each against this district's structural peers and the state.

    Includes how the district scored versus what its student demographics
    predict. That is a question worth asking about a district, never a verdict
    on it — the model explains only part of the spread, and the rest is real
    difference, local context and noise. See docs/WHAT_A_DOLLAR_BUYS.md."""
    data = _outcomes()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Outcomes data not built. Run scripts/build_outcomes_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        raise HTTPException(status_code=404, detail="District not in the outcomes dataset")
    return {"meta": data["meta"], **rec}


@app.get("/map", include_in_schema=False)
async def similarity_map():
    """Serve the statewide similarity map page."""
    page = STATIC_DIR / "map.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Map not available")


@app.get("/map-data", tags=["Districts"])
async def similarity_map_data():
    """Precomputed 2D similarity-map coordinates (PCA of the exogenous
    feature space; see scripts/graph_insights.py)."""
    data = STATIC_DIR / "map_data.json"
    if data.exists():
        return FileResponse(data, media_type="application/json")
    raise HTTPException(status_code=404, detail="Map data not built")


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

        # The biggest districts, so a first-time visitor has somewhere to click
        # instead of an empty search box.
        largest = await conn.fetch("""
            SELECT district_number, district_name, enrollment FROM v_finance_summary
            WHERE year = $1 AND enrollment > 0 ORDER BY enrollment DESC LIMIT 6
        """, stats["end_year"])

        return {**dict(stats), "largest_districts": [dict(r) for r in largest]}


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

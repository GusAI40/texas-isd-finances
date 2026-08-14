"""
FastAPI service for Texas School Finance Data Portal
"""
import asyncio
import json
import os
import time
import xml.sax.saxutils as saxutils
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from pydantic import BaseModel, Field

from . import (
    absences,
    analytics,
    llm_config,
    mcp_protocol,
    mcp_tools,
    migrations,
    scanner,
    site_gate,
    sources,
    tracking,
)
from . import format as fmt
from .sample_queries import SAMPLE_QUERIES

load_dotenv()

# Data coverage (TEA summarized financial data, fiscal years). Override via
# env if a new release extends the range.
MIN_YEAR = int(os.getenv("DATA_MIN_YEAR", "2009"))
MAX_YEAR = int(os.getenv("DATA_MAX_YEAR", "2025"))

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

# Browser origins allowed to POST /mcp. The check only fires when an Origin
# header is present, which means a direct API client or a desktop MCP host is
# unaffected; it exists so a random web page cannot use someone's browser as a
# confused deputy against a local instance (DNS rebinding). Empty disables it.
MCP_ALLOWED_ORIGINS = tuple(
    o.strip() for o in os.getenv(
        "MCP_ALLOWED_ORIGINS",
        "https://txisd.dev,https://claude.ai,http://localhost,http://127.0.0.1",
    ).split(",") if o.strip())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the database pool on startup, close it on shutdown.

    The app still boots when SUPABASE_DB_URL is unset so the portal page,
    /docs and /health remain reachable; data endpoints return 503 until the
    database is configured.
    """
    app.state.db_pool = None
    app.state.schema_status = "unknown"
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
        # Journey tracking creates its own tables. Until they exist every click
        # is dropped silently (visitor_event.rid is a FK), and the manual
        # alternative — pasting DDL into a dashboard — is a step that is easy to
        # believe you completed when you did not. One to_regclass lookup per
        # cold start; the DDL runs at most once per database. Never raises.
        app.state.schema_status = await migrations.ensure_schema(
            app.state.db_pool)
        print(f"schema: {app.state.schema_status}")
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

# CORS: this is a public, read-only API. Set CORS_ALLOW_ORIGINS to a
# comma-separated list to restrict origins.
#
# Credentials are off unconditionally. This used to be `"*" not in _origins`,
# which meant that narrowing the origin list — a tightening change — silently
# switched credentialed CORS on. There is no auth and no cookie to send, so
# the flag can only ever grant something unintended.
_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.middleware("http")
async def reject_scanner_probes(request: Request, call_next):
    """Turn away vulnerability scanners before any other work happens.

    Registered LAST so Starlette runs it FIRST: a probe never reaches the
    password gate, the page-view counter, the router, or the database. It was
    always going to 404; this makes that answer immediate and, more usefully,
    keeps the runtime log readable — about half of all requests to this site
    are one scanner hunting for WordPress, and real errors were drowning in it.

    404, never 403: a 403 tells an attacker something is there to protect.
    """
    if request.method in ("GET", "HEAD", "POST") and scanner.is_scanner_path(request.url.path):
        return Response(status_code=404, content='{"detail":"Not Found"}',
                        media_type="application/json",
                        headers={"Cache-Control": "no-store"})
    return await call_next(request)


@app.middleware("http")
async def site_password_gate(request: Request, call_next):
    """Keep the whole site private while SITE_PASSWORD is set.

    Registered LAST so Starlette runs it FIRST: a blocked request never reaches
    the page-view counter or any handler, so a locked site records no visits
    and does no database work.

    With SITE_PASSWORD unset this is a no-op and the portal is public — the
    normal state for a public-records site, and the state a misconfigured
    deploy falls back to.
    """
    if site_gate.should_block(request.url.path, request.headers.get("authorization")):
        return Response(
            content='{"detail":"This site is not open to the public yet."}',
            status_code=401,
            media_type="application/json",
            headers={
                # Prompts the browser for credentials rather than showing JSON.
                "WWW-Authenticate": 'Basic realm="Texas ISD Financial Resource Guide"',
                # A locked preview must never be indexed or cached publicly.
                "Cache-Control": "no-store",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline hardening, set by the app so it survives the deploy target.

    HSTS used to arrive only from Vercel's edge, which meant the Dockerfile and
    render.yaml paths in this repo shipped every other header and no HSTS. It
    is set here now, but only for requests that actually arrived over TLS —
    sending it over plain HTTP is meaningless, and pinning a developer's
    localhost to HTTPS for two years is a genuinely annoying thing to do.

    The CSP allows inline script and style because both pages are
    self-contained single files by design — no build step, no bundler, nothing
    to audit but the file itself. It still blocks any EXTERNAL script or frame,
    which is what actually matters for a page that renders public data.
    """
    resp = await call_next(request)
    if request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        return resp                      # Swagger UI loads its assets from a CDN
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if proto == "https":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    # /heatmap is the one page that loads Mapbox GL, so it gets a CSP widened
    # to exactly Mapbox's hosts and nothing more. Every other page keeps the
    # strict self-only policy — a hole punched for one route is not a hole in
    # the site. (The privacy-preserving /geomap is unchanged and stays strict.)
    if request.url.path == "/heatmap":
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' blob: https://api.mapbox.com; "
            "style-src 'self' 'unsafe-inline' https://api.mapbox.com; "
            "img-src 'self' data: blob: https://*.mapbox.com; "
            "worker-src blob:; child-src blob:; "
            "connect-src 'self' https://api.mapbox.com https://*.tiles.mapbox.com "
            "https://events.mapbox.com; "
            "frame-ancestors 'self'; base-uri 'self'; form-action 'self'",
        )
    else:
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
            "form-action 'self'",
        )
    return resp


# ---------------------------------------------------------------------------
# First-party usage counting. See src/analytics.py for what is deliberately NOT
# collected — in short, nothing that identifies a person.


async def _record_visit(pool, path: str, device: str, ref_host: str) -> None:
    """Bump today's counter for (path, device, referrer). Fails open: a metric
    is never worth failing a page view over."""
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.site_visits (day, path, device, referrer_host, hits) "
                "VALUES (current_date, $1, $2, $3, 1) "
                "ON CONFLICT (day, path, device, referrer_host) "
                "DO UPDATE SET hits = public.site_visits.hits + 1",
                path, device, ref_host)
    except Exception as exc:                       # table missing, DB asleep…
        print(f"WARNING: visit not counted: {exc}")


async def _log_question(pool, question: str, ok: bool, ms: int) -> None:
    """Store WHAT was asked, never WHO asked it.

    Knowing what Texans want to know about their schools is what should shape
    this site, so the question text is kept. Nothing accompanies it — no IP, no
    user-agent, no session or visitor id — so two questions can never be tied
    to each other or to a person. The site's privacy note says exactly this;
    keep them in step. Fails open: a log line is not worth losing an answer.
    """
    if pool is None:
        return
    text = analytics.clean_question(question)
    if not text:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.nlp_questions (question, ok, ms) VALUES ($1, $2, $3)",
                text, ok, ms)
    except Exception as exc:
        print(f"WARNING: question not logged: {exc}")


# ---------------------------------------------------------------------------
# Per-recipient journey tracking. The deliberate exception to everything above:
# see src/tracking.py for the entry condition (a minted ?rid= we mailed) and
# sql/create_visitor_tracking.sql for the fence around it.


def _pool_or_none(request: Request):
    """The pool, or None if the app never got one.

    `app.state.db_pool` is set by the lifespan, which does not run under some
    test clients and can fail outright when Supabase is paused. Reading the
    attribute directly raises AttributeError — and the open pixel lives inside
    an email, where a 500 renders as a visibly broken image in a
    superintendent's inbox. Every tracking path goes through here.
    """
    return getattr(request.app.state, "db_pool", None)


async def _record_event(pool, *, rid: str, visitor: str, session: str,
                        event: str, path: str | None = None,
                        district: str | None = None, dwell_ms: int | None = None,
                        ref_host: str = "", device: str = "",
                        user_agent: str | None = None,
                        ip: str | None = None) -> None:
    """Append one row to the recipient's stream. Fails open, loudly.

    The rid carries a foreign key to a minted recipient, so a forged token
    raises here rather than creating a stream for somebody who was never
    mailed. That is the intended behaviour and the reason the insert is not
    an upsert.
    """
    if pool is None or event not in tracking.EVENTS:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.visitor_event "
                "(rid, visitor_id, session_id, event, path, district_number, "
                " dwell_ms, referrer_host, device, user_agent, ip) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::inet)",
                rid, visitor, session, event, path, district, dwell_ms,
                ref_host, device, (user_agent or "")[:400] or None, ip)
    except Exception as exc:            # unminted rid, table missing, DB asleep
        print(f"WARNING: journey event not recorded ({event}): {exc}")


@app.middleware("http")
async def count_page_views(request: Request, call_next):
    """Count page views server-side: no script, no cookie, no third party.

    Only successful GETs of real page routes are counted, and only from
    non-bot clients — half this site's raw traffic is an exploit scanner, and
    counting it would make the numbers a lie. The write happens AFTER the
    response is produced and is wrapped so it can never break a page.
    """
    resp = await call_next(request)
    try:
        if request.method == "GET" and resp.status_code == 200:
            route = analytics.countable_path(request.url.path)
            if route:
                ua = request.headers.get("user-agent")
                if not analytics.is_bot(ua):
                    ref = analytics.referrer_host(
                        request.headers.get("referer"),
                        request.headers.get("host"))
                    # email clients strip referrers, so campaign links carry
                    # ?src=…; a real referrer wins over the tag if both exist
                    if not ref:
                        ref = analytics.source_tag(
                            request.query_params.get("src"))
                    device = analytics.device_of(ua)
                    await _record_visit(
                        _pool_or_none(request), route, device, ref)
                    await _track_journey(request, resp, route, device, ref, ua)
    except Exception as exc:
        print(f"WARNING: page-view counting failed: {exc}")
    return resp


async def _track_journey(request: Request, resp, route: str, device: str,
                         ref_host: str, ua: str | None) -> None:
    """Record an identified page view — but ONLY for a mailed recipient.

    `resume_or_start` returns None for everyone else, and that is the whole
    fence: an anonymous visitor has already been counted in site_visits above
    and leaves no other trace. A recipient arriving from the email carries
    ?rid=; from then on the cookie carries it, which is what makes a return
    visit next month attributable to the same person.
    """
    bound = tracking.resume_or_start(
        request.cookies.get(tracking.COOKIE_NAME),
        request.query_params.get("rid"))
    if bound is None:
        return
    rid, visitor, session, is_new_session = bound
    from_email = bool(tracking.valid_token(request.query_params.get("rid")))

    # The click itself is a distinct event from the page view it caused: the
    # first tells you the email worked, the second where they landed.
    if from_email:
        await _record_event(
            _pool_or_none(request), rid=rid, visitor=visitor, session=session,
            event="click", path=route,
            district=request.query_params.get("d"), ref_host=ref_host,
            device=device, user_agent=ua,
            ip=tracking.client_ip(request.headers.get("x-forwarded-for"),
                                  request.client.host if request.client else None))
    elif is_new_session:
        # No token in the URL and the last sitting has aged out: they came back
        # on their own. That is the most interesting event in the whole stream.
        await _record_event(
            _pool_or_none(request), rid=rid, visitor=visitor, session=session,
            event="return", path=route, ref_host=ref_host, device=device)

    await _record_event(
        _pool_or_none(request), rid=rid, visitor=visitor, session=session,
        event="pageview", path=route,
        district=request.query_params.get("d"), ref_host=ref_host, device=device,
        user_agent=ua,
        ip=tracking.client_ip(request.headers.get("x-forwarded-for"),
                              request.client.host if request.client else None))

    resp.set_cookie(
        tracking.COOKIE_NAME,
        tracking.build_cookie(rid, visitor, session),
        max_age=tracking.COOKIE_MAX_AGE,
        httponly=True,      # the beacon posts the path, not the identity
        secure=True,
        samesite="lax")     # must survive the cross-site hop from the mail client

    # A contentless companion the page script CAN read, so the dwell beacon
    # knows whether to run at all. It carries no identity — just "you are in
    # the tracked population" — which keeps the rid out of JavaScript entirely
    # while sparing every anonymous visitor a pointless POST to /e.
    resp.set_cookie(
        "txj_on", "1", max_age=tracking.COOKIE_MAX_AGE,
        httponly=False, secure=True, samesite="lax")


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
async def portal(request: Request):
    """Serve the public portal page — with per-district search + social
    metadata injected server-side when ?d=NNNNNN is present.

    The blind spot this closes: crawlers and link-preview scrapers do not run
    the client JS, so every district URL used to serve byte-identical HTML —
    the same title, the homepage canonical, a generic OG card, and no district
    name anywhere they could see it. Now the head carries the district's name,
    an honest headline, its canonical, its share image, and JSON-LD, all read
    from the committed artefacts (no database — survives a paused Supabase).
    The client app below the head is untouched.
    """
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return {"message": "Texas School Finance API", "documentation": "/docs"}
    num = request.query_params.get("d")
    try:
        from src import og
        html = og.render_head(index.read_text(encoding="utf-8"),
                              num if num else None)
        return HTMLResponse(html, headers={
            "Cache-Control": "public, max-age=600, must-revalidate"})
    except Exception:  # noqa: BLE001 — never let meta injection break the page
        return FileResponse(index)


# A 1x1 transparent GIF, inline so the open pixel needs no file on disk.
_PIXEL_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000"
    "010001000002024401003b")


@app.get("/px/{rid}.gif", include_in_schema=False)
async def open_pixel(rid: str, request: Request):
    """Records that a mailed email was opened, then returns a 1x1 GIF.

    Resend reports opens too, but only while the message is inside its
    retention window and only if the domain's tracking toggle happens to be
    on — a switch that silently zeroed 71 sends in wave 1. This is our own
    copy, in our own database, keyed to the recipient.

    Caveat worth remembering when reading the numbers: mail clients that
    prefetch images (Apple Mail Privacy Protection, most corporate scanners)
    trip this pixel without a human present. An open is evidence the message
    was delivered somewhere real, not proof it was read.
    """
    token = tracking.valid_token(rid)
    if token:
        ua = request.headers.get("user-agent")
        await _record_event(
            _pool_or_none(request), rid=token,
            visitor=tracking.new_visitor_id(), session=tracking.new_session_id(),
            event="email_open", device=analytics.device_of(ua), user_agent=ua,
            ip=tracking.client_ip(request.headers.get("x-forwarded-for"),
                                  request.client.host if request.client else None))
    return Response(_PIXEL_GIF, media_type="image/gif", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache"})


class DwellBeacon(BaseModel):
    path: str = Field(..., max_length=120)
    ms: int = Field(..., ge=0)
    d: Optional[str] = Field(None, max_length=12)


@app.post("/e", include_in_schema=False)
async def dwell_beacon(beacon: DwellBeacon, request: Request):
    """How long a tracked recipient stayed on a page.

    The browser posts this on pagehide/visibilitychange via sendBeacon. The
    identity is NOT in the body — it comes from the httpOnly cookie, so a page
    script cannot read it and a third party cannot forge one for a recipient
    whose token they do not have.

    Always 204, whatever happens: a beacon is fire-and-forget and the client
    is usually mid-unload with nobody left to read an error.
    """
    rid, visitor, session, _ = tracking.parse_cookie(
        request.cookies.get(tracking.COOKIE_NAME))
    dwell = tracking.clean_dwell(beacon.ms)
    if rid and dwell and analytics.countable_path(beacon.path):
        await _record_event(
            _pool_or_none(request), rid=rid, visitor=visitor, session=session,
            event="dwell", path=analytics.countable_path(beacon.path),
            district=beacon.d, dwell_ms=dwell)
    return Response(status_code=204)


@app.get("/share/{name}", include_in_schema=False)
async def share_image(name: str):
    """Per-district 1200x630 social card (and the default). Pre-rendered into
    static/share/ at build time by scripts/build_share_cards.py; falls back to
    the default card for any district without one so a link is never
    imageless."""
    if not name.endswith(".png") or "/" in name or ".." in name:
        raise HTTPException(status_code=404, detail="Not found")
    p = STATIC_DIR / "share" / name
    if not p.exists():
        p = STATIC_DIR / "share" / "default.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Share image not built")
    return FileResponse(p, media_type="image/png", headers={
        "Cache-Control": "public, max-age=86400, must-revalidate"})


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
            "district_economics": "GET /district/{district_number}/economics",
            "texas_economics": "GET /economics/texas",
            "district_bonds": "GET /district/{district_number}/bonds",
            "texas_bonds": "GET /bonds/texas",
            "district_equity": "GET /district/{district_number}/equity",
            "texas_equity": "GET /equity/texas",
            "houston_takeover": "GET /takeover/houston",
            "anomalies": "GET /anomalies",
            "sample_queries": "GET /sample-queries",
            "stats": "GET /stats",
            "health": "GET /health",
        },
    }


# Rate limiting for /query, where every call costs a paid OpenAI request.
#
# There are two layers, and only one of them is a real spend guard.
#
# The per-IP window below is per-process and stays that way on purpose: it
# exists to stop one honest user hammering the box, and it cannot do more
# than that, because X-Forwarded-For is client-supplied. An attacker presents
# a fresh IP per request and walks straight through it.
#
# The ceiling that actually bounds the bill is _shared_limit_reached(), which
# counts in the DATABASE. It used to count in process memory, which on Vercel
# meant every warm instance enforced its own separate ceiling — "60 per
# minute" was really "60 per minute per instance", and the platform starts as
# many instances as traffic demands. That is not a bound.
_RATE_LIMIT = int(os.getenv("QUERY_RATE_LIMIT", "10"))       # per IP, per minute
_RATE_WINDOW = 60.0
_rate_buckets: Dict[str, List[float]] = {}

_GLOBAL_LIMIT = int(os.getenv("QUERY_GLOBAL_LIMIT", "60"))   # all callers, per minute
_DAILY_LIMIT = int(os.getenv("QUERY_DAILY_LIMIT", "5000"))   # all callers, per day
_global_hits: List[float] = []

# Atomic: increment only while still under the cap, and report whether we did.
# Doing it in one statement is the whole point — a read-then-write race across
# instances is exactly the hole this is meant to close. No row returned means
# the window is full.
_CLAIM_SQL = """
    INSERT INTO public.nlp_usage (window_kind, window_start, calls)
    VALUES ($1, date_trunc($2, now()), 1)
    ON CONFLICT (window_kind, window_start)
    DO UPDATE SET calls = public.nlp_usage.calls + 1
    WHERE public.nlp_usage.calls < $3
    RETURNING calls
"""


async def _shared_limit_reached(pool) -> bool:
    """Claim one call against the minute and day ceilings shared by every instance.

    Returns True when a ceiling is reached and the call must be refused.

    Falls back to the in-memory counters when the database is unreachable or
    the table has not been created. That is a deliberate choice: /query's own
    connection is separate from this one, so a metering outage would otherwise
    take down a working feature. It fails OPEN on availability and the
    per-instance ceiling still applies, so the exposure is the old behaviour,
    not a new one — and `sql/create_nlp_usage.sql` is a one-time setup step.
    """
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            for kind, trunc, cap in (("minute", "minute", _GLOBAL_LIMIT),
                                     ("day", "day", _DAILY_LIMIT)):
                got = await conn.fetchval(_CLAIM_SQL, kind, trunc, cap)
                if got is None:
                    return True
    except Exception as exc:  # pragma: no cover - depends on environment
        print(f"WARNING: shared rate limit unavailable, using per-instance only: {exc}")
        return False
    return False


def _rate_limited(ip: str) -> bool:
    """Per-IP and per-instance limits. Cheap, synchronous, and not the real guard."""
    now = time.monotonic()
    global _global_hits
    _global_hits = [t for t in _global_hits if now - t < _RATE_WINDOW]
    if len(_global_hits) >= _GLOBAL_LIMIT:
        return True

    bucket = [t for t in _rate_buckets.get(ip, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        _rate_buckets[ip] = bucket
        return True
    bucket.append(now)
    _rate_buckets[ip] = bucket
    _global_hits.append(now)
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
    # Checked before the engine is built, so a refused call costs nothing —
    # no OpenAI client, no database connection for the agent, no tokens.
    if await _shared_limit_reached(http_request.app.state.db_pool):
        raise HTTPException(
            status_code=429,
            detail=("This service has reached its shared limit of questions for now. "
                    "Every other page works — only the question box is paused. "
                    "Please try again later."),
        )
    try:
        engine = get_nlp_engine()
    except Exception:
        # Name the key the CONFIGURED provider actually needs — telling a
        # DeepSeek deploy to set OPENAI_API_KEY sends the operator in circles.
        raise HTTPException(
            status_code=503,
            detail=(f"NLP engine not configured. Set "
                    f"{llm_config.resolve_llm_config().key_env_name} and NLP_DB_URL."),
        )
    # engine.query() is synchronous and can take ~10s. Awaiting it directly
    # blocked the event loop, so one slow question stalled every other request
    # on the instance. Off to a worker thread, with a hard ceiling so a hung
    # model call cannot pin a thread forever.
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(engine.query, request.question),
            timeout=float(os.getenv("QUERY_TIMEOUT_SECONDS", "45")),
        )
    except asyncio.TimeoutError:
        await _log_question(http_request.app.state.db_pool, request.question,
                            ok=False, ms=int((time.monotonic() - started) * 1000))
        raise HTTPException(
            status_code=504,
            detail="That question took too long to answer. Try a narrower one.",
        )
    # `ok` records whether the question was actually ANSWERED, not merely that
    # it avoided a timeout. The engine returns success=False with an error for
    # things like an exhausted OpenAI balance, and logging those as successes
    # would hide an outage in the very table meant to reveal one.
    await _log_question(http_request.app.state.db_pool, request.question,
                        ok=bool(result.get("success")),
                        ms=int((time.monotonic() - started) * 1000))
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
            return {"turnarounds": [], "peers_scanned": 0,
                    "absence": absences.no_peer_turnaround(
                        _district_name(district_number), 0)}

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
        return {
            "turnarounds": results, "peers_scanned": len(by_peer),
            # An empty list is the more interesting answer here: it means
            # nobody like you got out of this, which is worth knowing
            # before anyone claims there is a local example to follow.
            "absence": None if results else absences.no_peer_turnaround(
                names.get(district_number) or _district_name(district_number),
                len(by_peer)),
        }


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
                    "note": "Not enough comparable peers for benchmarking.",
                    "absence": absences.no_insights(
                        _district_name(district_number), len(peers))}

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
            # No insight is itself an answer: this district spends where its
            # peers spend. That read as a blank box before.
            "absence": None if insights else absences.no_insights(
                me["district_name"], len(peers)),
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


_economics_cache: Optional[Dict[str, Any]] = None


def _economics() -> Optional[Dict[str, Any]]:
    global _economics_cache
    if _economics_cache is None:
        path = STATIC_DIR / "economics_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _economics_cache = json.load(fh)
    return _economics_cache


@app.get("/district/{district_number}/economics", tags=["Districts"])
async def get_district_economics(district_number: str):
    """What you pay, where it goes, what it buys, and who does better.

    Four things a tax statement cannot tell you: the school tax on a $300,000
    home in this district and how much of it leaves under recapture; how the
    budget splits between teaching and servicing debt, including that debt in
    teacher-equivalents; how reliably this district beats what its student need
    predicts, measured over eleven years rather than one; and the named
    districts of the same size and student need that do so more reliably.

    `tax` is null for charters, which levy no property tax, and for any
    district where two independent estimates of its tax base disagree by more
    than 25% — a wrong number on someone's tax bill is worse than no number.
    """
    data = _economics()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Economics data not built. Run scripts/build_economics_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        raise HTTPException(status_code=404, detail="District not in the economics dataset")
    # A null tax block was rendering as a blank with nothing to explain it. The
    # forensic layer already worked out whether that is "charter, levies none"
    # or "withheld, estimates disagreed" — two opposite meanings — so reuse it
    # rather than deriving the same sentence twice.
    fx = (_forensics() or {}).get("districts", {}).get(district_number) or {}
    return {"meta": data["meta"], "micro": data["micro"],
            "absences": fx.get("absences", []), **rec}


@app.get("/economics/texas", tags=["Statewide"])
async def get_texas_economics():
    """The statewide series behind every district page.

    Per-student spending in constant dollars beside nominal, the split of the
    school tax rate between operating and debt over nineteen years, recapture
    by year and how concentrated it is, and the measured return on each lever
    a district actually controls. Serves with no database.
    """
    data = _economics()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Economics data not built. Run scripts/build_economics_data.py")
    return {"meta": data["meta"], "macro": data["macro"], "micro": data["micro"]}


_bonds_cache: Optional[Dict[str, Any]] = None


def _bonds() -> Optional[Dict[str, Any]]:
    global _bonds_cache
    if _bonds_cache is None:
        path = STATIC_DIR / "bond_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _bonds_cache = json.load(fh)
    return _bonds_cache


@app.get("/district/{district_number}/bonds", tags=["Districts"])
async def get_district_bonds(district_number: str):
    """Every bond this district ever put on a ballot, and how the vote went.

    TEA's financial data can say how much a district spends servicing debt but
    not what the debt was for — it does not itemise facilities, so a stadium is
    not separable from a roof. The ballot is the only public record that names
    what the money bought, with a date and a vote count attached.

    Returns each proposition (date, stated purpose, amount asked, carried or
    defeated, votes for and against) plus this district's totals, and the
    statewide context needed to read them.
    """
    data = _bonds()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Bond data not built. Run scripts/build_bond_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="No bond election on record for this district. Districts that have "
                   "never gone to the voters for debt have no entry here.")
    return {"meta": data["meta"], "did_it_work": data.get("did_it_work"), "context": {
        "by_purpose": data["by_purpose"], "by_era": data["by_era"],
        "bundling": data["bundling"], "stadium": data["stadium"]}, **rec}


@app.get("/bonds/texas", tags=["Statewide"])
async def get_texas_bonds():
    """66 years of Texas school bond elections, without the per-district detail.

    Pass rate by stated purpose, the shift in what districts ask for and what
    voters approve, and what bundling a stadium with classrooms does to both
    the odds and the size of the ask.
    """
    data = _bonds()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Bond data not built. Run scripts/build_bond_data.py")
    return {k: v for k, v in data.items() if k != "districts"}


def _district_name(num: str) -> str:
    """A readable name without a database round trip — the absence sentences
    need one and the fallback index already carries every district."""
    data = _fallback_index()
    if data:
        for r in data.get("districts", []):
            if r.get("district_number") == num:
                return fmt.district_name(r.get("district_name") or num)
    return f"District {num}"


_forensics_cache: Optional[Dict[str, Any]] = None


def _forensics() -> Optional[Dict[str, Any]]:
    global _forensics_cache
    if _forensics_cache is None:
        path = STATIC_DIR / "forensic_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _forensics_cache = json.load(fh)
    return _forensics_cache


@app.get("/district/{district_number}/forensics", tags=["Districts"])
async def get_district_forensics(district_number: str):
    """The four money questions Texas reports in four incompatible places.

    What sits OUTSIDE the operating total (debt service is not in it, so a
    district can look lean on instruction while carrying the state's heaviest
    debt); who actually pays, from GROSS local collections rather than the
    net-of-recapture figure TEA publishes; what the ballot said the debt was
    for, which is the only public itemisation of school facilities that exists;
    and where the results landed against what this district's own student need
    predicts.

    `flags` are descriptions, not accusations: each one states a published
    number against a threshold that is published beside it in `meta.thresholds`.
    There is deliberately no combined score — the four measures are unrelated
    and adding them would invent a ranking the data cannot support.
    """
    data = _forensics()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Forensic data not built. Run scripts/build_forensic_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        raise HTTPException(status_code=404, detail="District not in the forensic dataset")
    return {"meta": data["meta"], "statewide": data["statewide"], **rec}


@app.get("/forensics/texas", tags=["Statewide"])
async def get_texas_forensics():
    """Statewide totals, the ranked tables, and one compact row per district.

    `table` carries every district so the page can sort and filter without a
    round trip; the full per-district file is at
    `/district/{district_number}/forensics`. Serves with no database.
    """
    data = _forensics()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Forensic data not built. Run scripts/build_forensic_data.py")
    return {k: v for k, v in data.items() if k != "districts"}


_fallback_cache: Optional[Dict[str, Any]] = None


def _fallback_index() -> Optional[Dict[str, Any]]:
    """Parsed form of fallback_index.json, for callers that need the districts
    rather than the bytes. The /fallback-index endpoint still streams the file
    with FileResponse — parsing it there would cost every visitor nothing but
    latency."""
    global _fallback_cache
    if _fallback_cache is None:
        path = STATIC_DIR / "fallback_index.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _fallback_cache = json.load(fh)
    return _fallback_cache


_trends_cache: Optional[Dict[str, Any]] = None


def _trends() -> Optional[Dict[str, Any]]:
    global _trends_cache
    if _trends_cache is None:
        path = STATIC_DIR / "trend_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _trends_cache = json.load(fh)
    return _trends_cache


@app.get("/district/{district_number}/trends", tags=["Districts"])
async def get_district_trends(district_number: str):
    """Seventeen fiscal years of this district, against the state's own line.

    Every other view on this site reports one year, which can tell a board
    where it stands but not which way it is moving. This returns the series
    for six measures — instruction's share of the operating dollar, instruction
    per student, debt service, security, operating balance and federal revenue
    — in constant 2024 dollars, plus each measure's first-to-last change and
    how that change compares with the statewide one.

    `vs_state.steeper_than_state` is true when this district is moving in the
    worrying direction faster than Texas as a whole. It describes a direction,
    not a cause: a falling instruction share can be a district cutting
    classrooms or a district opening them, and this data cannot tell the two
    apart.

    Districts under 500 students carry `small_district`, because one retirement
    moves their per-student figures more than a policy would.
    """
    data = _trends()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Trend data not built. Run scripts/build_trend_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="No trend for this district. Districts reporting fewer than eight of "
                   "the seventeen years are excluded — too little to call a trend.")
    return {"meta": data["meta"], "statewide": data["statewide"], **rec}


@app.get("/trends/texas", tags=["Statewide"])
async def get_texas_trends():
    """The seventeen-year statewide series and the six findings in it.

    Carries the balanced-panel check: every headline was re-derived on only the
    districts reporting in both the first and last year, so a trend cannot be
    an artefact of which districts report. Serves with no database.
    """
    data = _trends()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Trend data not built. Run scripts/build_trend_data.py")
    return {k: v for k, v in data.items() if k != "districts"}


_equity_cache: Optional[Dict[str, Any]] = None


def _equity() -> Optional[Dict[str, Any]]:
    global _equity_cache
    if _equity_cache is None:
        path = STATIC_DIR / "equity_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _equity_cache = json.load(fh)
    return _equity_cache


@app.get("/district/{district_number}/equity", tags=["Districts"])
async def get_district_equity(district_number: str):
    """How this district does for the students it actually serves.

    A district average hides who it is failing. This reports how the district's
    economically disadvantaged students do at TEA's Meets grade level bar, and
    where that places them among poor students statewide — plus the same for
    emergent bilingual and special education students, the reading/maths split,
    and the change since last year.

    The poor/non-poor gap is included but is deliberately NOT the headline: it
    correlates about zero with how well poor students actually do, because the
    narrowest gaps belong to districts where nobody does well.
    """
    data = _equity()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Equity data not built. Run scripts/build_equity_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="This district does not have enough tests from economically "
                   "disadvantaged students to report a reliable figure.")
    return {"meta": data["meta"], "state": data["state"],
            "state_by_subject": data["state_by_subject"], "leaders": data["leaders"], **rec}


@app.get("/equity/texas", tags=["Statewide"])
async def get_texas_equity():
    """Statewide results by student group, and who does best for poor students."""
    data = _equity()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Equity data not built. Run scripts/build_equity_data.py")
    return {k: v for k, v in data.items() if k != "districts"}


_takeover_cache: Optional[Dict[str, Any]] = None


def _takeover() -> Optional[Dict[str, Any]]:
    global _takeover_cache
    if _takeover_cache is None:
        path = STATIC_DIR / "takeover_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _takeover_cache = json.load(fh)
    return _takeover_cache


@app.get("/takeover/houston", tags=["Statewide"])
async def get_houston_takeover():
    """Did the June 2023 state takeover of Houston ISD change results?

    Houston's own before-and-after cannot answer that: every Texas district was
    climbing out of the same pandemic hole at the same time. This compares
    Houston with districts that were in the same hole and were not taken over —
    at least 40,000 students and at least 60% economically disadvantaged as of
    2023, chosen on pre-takeover traits so the comparison cannot be picked to
    fit the answer.

    Ships the checks alongside the result: whether the pre-takeover trends were
    parallel, where Houston's swing ranks against the same calculation run on
    every Texas district, whether its student body changed, and which student
    groups the gains did and did not reach.

    One treated district means no meaningful p-value, and none is claimed.
    """
    data = _takeover()
    if data is None:
        raise HTTPException(status_code=503,
                            detail="Takeover analysis not built. Run scripts/build_takeover_data.py")
    return data


@app.get("/static/design.css", include_in_schema=False)
async def design_stylesheet():
    """The shared design system, linked by every page.

    Served explicitly rather than by mounting the whole static/ directory:
    that directory also holds the committed data artefacts (district_geo.json,
    outcomes_data.json and friends), and a blanket mount would expose the lot
    at guessable URLs. One asset, one route.

    Long cache with revalidation — the file is small and changes rarely, but a
    stale palette would be visible on every page, so it must not be cached
    immutably.
    """
    css = STATIC_DIR / "design.css"
    if not css.exists():
        raise HTTPException(status_code=404, detail="Stylesheet not found")
    return FileResponse(css, media_type="text/css",
                        headers={"Cache-Control": "public, max-age=3600, must-revalidate"})


@app.get("/static/track.js", include_in_schema=False)
async def track_script():
    """The dwell beacon. Inert for everyone except a mailed recipient — it
    returns immediately unless the server has set the `txj_on` flag cookie.
    Same one-asset, one-route policy as the stylesheet above."""
    js = STATIC_DIR / "track.js"
    if not js.exists():
        raise HTTPException(status_code=404, detail="Script not found")
    return FileResponse(js, media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=3600, must-revalidate"})


@app.get("/static/tag-pipeline.png", include_in_schema=False)
async def tag_pipeline_graphic():
    """The TAG ai intelligence-layer graphic, hot-linked by the superintendent
    outreach emails (scripts/send_outreach.py) — an email can't bundle its own
    images, so the asset has to live at a stable public URL. Same one-asset,
    one-route policy as the stylesheet above."""
    png = STATIC_DIR / "tag_pipeline.png"
    if not png.exists():
        raise HTTPException(status_code=404, detail="Graphic not found")
    return FileResponse(png, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400, must-revalidate"})


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    """Let search engines in, and point them at the district index."""
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /query\n"          # the paid AI path — no crawler budget on it
        "Sitemap: https://txisd.dev/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    """Every district is a page worth finding. Without this, a search for
    "is <name> ISD good" can never reach us — the district views are rendered
    client-side from ?d=, so crawlers need to be told they exist."""
    urls = ["https://txisd.dev/", "https://txisd.dev/about", "https://txisd.dev/feed",
            "https://txisd.dev/forensics", "https://txisd.dev/sources",
            "https://txisd.dev/geomap",
            "https://txisd.dev/map", "https://txisd.dev/docs"]
    data = _outcomes()
    if data:
        urls += [f"https://txisd.dev/?d={n}" for n in sorted(data["districts"])]
    body = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
            + "".join(f"<url><loc>{u}</loc></url>" for u in urls)
            + "</urlset>")
    return Response(content=body, media_type="application/xml")


@app.get("/intel", include_in_schema=False)
async def intel_page():
    """The daily ISD intelligence briefing, rendered."""
    page = STATIC_DIR / "intel.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Intelligence page not available")


@app.get("/feed", include_in_schema=False)
async def feed_page():
    """The Feed: the day's district headlines as a stream, each with the
    receipts. Same /briefing data as /intel, styled as a reverse-chron feed."""
    page = STATIC_DIR / "feed.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Feed not available")


def _atom_escape(text: Any) -> str:
    """Escape a value for use in Atom XML text content or attribute values."""
    return saxutils.escape(str(text or ""), {'"': "&quot;", "'": "&apos;"})


def _atom_updated(value: Any, fallback: Any = "") -> str:
    """Coerce a briefing date into RFC 3339, which Atom requires.

    Briefing dates are bare days ("2026-01-10"); a feed reader needs a full
    timestamp. Anything unparseable falls back to the run date rather than
    emitting an invalid document."""
    for candidate in (value, fallback, "1970-01-01"):
        raw = str(candidate or "").strip()
        if not raw:
            continue
        if len(raw) == 10:  # YYYY-MM-DD → midnight UTC
            raw += "T00:00:00Z"
        try:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Timezone-naive timestamps get an explicit UTC marker.
        if not (raw.endswith("Z") or "+" in raw[10:] or "-" in raw[10:]):
            raw += "Z"
        return raw
    return "1970-01-01T00:00:00Z"


def build_atom_feed(briefing: Dict[str, Any]) -> str:
    """Render the daily briefing as an Atom feed document.

    Same data the /feed page shows, in the format feed readers and aggregators
    actually poll. Entries that resolved to a district deep-link its portal
    view (/?d=NUM); the rest link the human feed page. Capped at the 50 newest
    entries, newest first. Pure function of the briefing dict, so tests can
    exercise it offline without a server or a database.
    """
    meta = briefing.get("meta") or {}
    run_date = str(meta.get("run_date") or "")
    findings = list(briefing.get("top_findings") or [])
    # Reverse-chron by published date; ISO date strings sort lexicographically
    # and the sort is stable, so same-day stories keep the briefing's ranking.
    findings.sort(key=lambda f: str(f.get("published_at") or run_date), reverse=True)
    findings = findings[:50]

    feed_updated = _atom_updated(
        max((str(f.get("published_at") or "") for f in findings), default=run_date)
        or run_date, run_date)
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        "<title>Texas ISD — The Feed</title>",
        "<subtitle>What's happening across Texas school districts, every headline "
        "with the receipts from 17 years of official state data.</subtitle>",
        "<id>https://txisd.dev/feed</id>",
        '<link rel="alternate" type="text/html" href="https://txisd.dev/feed"/>',
        '<link rel="self" type="application/atom+xml" href="https://txisd.dev/feed.xml"/>',
        f"<updated>{feed_updated}</updated>",
        "<author><name>Texas ISD Finances (txisd.dev)</name></author>",
    ]
    for i, f in enumerate(findings):
        title = f.get("headline") or f.get("hook") or "Texas ISD update"
        summary = f.get("summary") or f.get("what_our_data_says") or f.get("hook") or title
        district = str(f.get("district_number") or "").strip()
        link = f"https://txisd.dev/?d={district}" if district else "https://txisd.dev/feed"
        # content_hash is the pipeline's stable identity for a story; entries
        # without one get a positional id scoped to the run date.
        entry_id = f"https://txisd.dev/feed#{f.get('content_hash') or f'{run_date}-{i}'}"
        parts += [
            "<entry>",
            f"<title>{_atom_escape(title)}</title>",
            f"<id>{_atom_escape(entry_id)}</id>",
            f'<link rel="alternate" type="text/html" href="{_atom_escape(link)}"/>',
            f"<updated>{_atom_updated(f.get('published_at'), run_date)}</updated>",
            f"<summary>{_atom_escape(summary)}</summary>",
            "</entry>",
        ]
    parts.append("</feed>")
    return "".join(parts)


@app.get("/feed.xml", include_in_schema=False)
async def feed_xml(request: Request):
    """The Feed as Atom, for feed readers. Same DB-then-snapshot lookup as
    /briefing, so it works with no database at all."""
    briefing: Optional[Dict[str, Any]] = None
    pool = request.app.state.db_pool
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT payload FROM public.isd_briefings ORDER BY run_date DESC LIMIT 1")
                if row:
                    briefing = json.loads(row["payload"])
        except Exception as exc:  # table missing or DB down → fall through to file
            print(f"WARNING: briefing table unavailable for feed.xml, using snapshot: {exc}")
    if briefing is None:
        snap = STATIC_DIR / "isd_briefing.json"
        if snap.exists():
            briefing = json.loads(snap.read_text(encoding="utf-8"))
    if briefing is None:
        raise HTTPException(status_code=404,
                            detail="No briefing yet. Run the daily research "
                                   "(see docs/ISD_INTELLIGENCE.md).")
    return Response(content=build_atom_feed(briefing),
                    media_type="application/atom+xml; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=900"})


@app.get("/.well-known/mcp.json", include_in_schema=False)
async def well_known_mcp():
    """MCP discovery: tells an assistant (or a registry crawler) where this
    site's Model Context Protocol endpoint lives. The scanner middleware
    whitelists exactly this path (src/scanner.py) — everything else under
    /.well-known/ except security.txt is still fast-rejected."""
    return JSONResponse({
        "mcpServers": {
            "texas-isd": {
                "url": "https://txisd.dev/mcp",
                "transport": "http",
                "description": (
                    "Read-only tools over Texas school district finances "
                    "(TEA PEIMS, fiscal 2009–2025): find districts, money, "
                    "forensics, trends, bonds, debt, campuses, comparisons."),
            }
        },
        "description": "Texas ISD Finances MCP server — official state data, "
                       "every result carries its caveats.",
        "documentation": "https://txisd.dev/transparency",
    }, headers={"Cache-Control": "public, max-age=3600"})


@app.post("/mcp", include_in_schema=False)
async def mcp_endpoint(request: Request):
    """Model Context Protocol 2026-07-28, so an assistant can answer questions
    about Texas school money from the state's own records instead of guessing.

    Stateless by construction: no handshake, no session id, no server-initiated
    requests. That is what makes it possible here at all — this app runs behind
    a round-robin with no sticky routing, and every earlier MCP revision
    required session affinity.

    Read-only. Every tool reads a committed JSON artefact, so nothing here
    touches the database, spends an LLM token, or can be prompt-injected. See
    src/mcp_protocol.py for the wire format and src/mcp_tools.py for the tools.
    """
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    status, body = mcp_protocol.handle(
        raw, headers,
        call_tool=mcp_tools.call_tool,
        list_tools=mcp_tools.list_tools,
        instructions=mcp_tools.instructions(),
        allowed_origins=MCP_ALLOWED_ORIGINS,
    )
    if body is None:                      # a notification: 202, no content
        return Response(status_code=status)
    return JSONResponse(status_code=status, content=body,
                        headers={"Cache-Control": "no-store"})


@app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
async def mcp_endpoint_rejected():
    """2026-07-28 removed the GET stream and the DELETE session teardown. The
    spec asks a server that implements only this revision to answer 405 so an
    older client fails fast instead of hanging on a stream that never opens."""
    return JSONResponse(
        status_code=405, content=mcp_protocol.legacy_initialize_error(),
        headers={"Allow": "POST", "Cache-Control": "no-store"})


_quality_cache: Optional[Dict[str, Any]] = None


def _forensic_quality() -> Optional[Dict[str, Any]]:
    global _quality_cache
    if _quality_cache is None:
        path = STATIC_DIR / "forensic_quality.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _quality_cache = json.load(fh)
    return _quality_cache


@app.get("/forensics/quality", tags=["Statewide"])
async def get_forensic_quality():
    """Forensic-accounting tests on the filings themselves.

    Three questions a forensic accountant asks of any book of account, applied
    to 20,587 district-years of TEA's own data:

    **Do the numbers look real?** Benford's Law across all 1.2M filed figures —
    MAD 0.0004, close conformity. The per-district version is deliberately NOT
    published: run naively it labels 1,104 of 1,211 districts "nonconforming",
    and a null simulation shows perfect Benford data scores the same way at
    these sample sizes. The refusal ships with its evidence.

    **Does each filing add up?** Objects and revenue reconcile for 100% of
    district-years; functions for 98.83%, and the gaps are named.

    **Who approved the debt?** Texas permits school debt with no election, and
    TEA does not record how debt was authorised. Districts paying debt service
    with no voter-approved bond in the ballot record are listed.

    None of this is evidence of wrongdoing, and every payload says so. What
    these have in common is that the public record does not answer an obvious
    question. Serves with no database.
    """
    data = _forensic_quality()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Forensic quality data not built. Run scripts/build_forensic_quality.py")
    return data


_debt_cache: Optional[Dict[str, Any]] = None


def _debt() -> Optional[Dict[str, Any]]:
    global _debt_cache
    if _debt_cache is None:
        path = STATIC_DIR / "debt_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _debt_cache = json.load(fh)
    return _debt_cache


@app.get("/debt/texas", tags=["Statewide"])
async def get_texas_debt():
    """What Texas school districts still OWE — the stock, not the yearly payment.

    Every other debt figure on this site comes from PEIMS and is a flow: what a
    district paid out in one year. This is the balance. As of fiscal 2025 Texas
    school districts owed **$236.7 billion** — $148.4B of principal not yet
    repaid and **$88.3B of interest nobody has paid yet**, 37.3% of the whole.
    On debt already sold, it clears in **2061**.

    Split by instrument, because the two are not the same promise:

    **CIB** — current interest bonds. Interest paid twice a year, as expected.

    **CAB** — capital appreciation bonds. Nothing is paid until maturity;
    interest compounds for the life of the bond and lands in a lump at the end.
    169 districts still carry them, with **$2.36B of interest deferred** against
    $440m of principal outstanding. Texas capped the practice in 2015, but bonds
    sold before then are still owed.

    Dollars repaid per dollar borrowed is reported at each district's **peak**
    year, never the current one: on a shrinking balance that ratio rises by
    itself (Leander ISD reads 4.5x in 2014 and would read 396x in 2030 with
    nothing having changed), so the current-year figure would be fiction.

    Borrowing to build schools is lawful and ordinary. None of this is evidence
    of wrongdoing. Serves with no database.
    """
    data = _debt()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Debt data not built. Run scripts/ingest_brb_debt.py then "
                   "scripts/build_debt_data.py")
    return {"meta": data["meta"], **data["texas"]}


@app.get("/district/{district_number}/debt", tags=["Districts"])
async def get_district_debt(district_number: str):
    """What one district still owes, and the year it clears.

    Principal and interest outstanding, the interest share, the per-student
    balance, the history of the balance since 2005, and — where the district
    sold capital appreciation bonds — the interest deferred to maturity and the
    terms at its peak year.

    Districts the Bond Review Board tracks no debt for return an `absence`
    saying so rather than an empty object: carrying no bonded debt is a finding
    about a district, not missing data.
    """
    data = _debt()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Debt data not built. Run scripts/ingest_brb_debt.py then "
                   "scripts/build_debt_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        name = _district_name(district_number) or district_number
        return {"district_number": district_number, "district_name": name,
                "meta": data["meta"],
                "absence": absences.no_debt_outstanding(name)}
    return {"district_number": district_number, "meta": data["meta"], **rec}


_campus_cache: Optional[Dict[str, Any]] = None


def _campuses() -> Optional[Dict[str, Any]]:
    global _campus_cache
    if _campus_cache is None:
        path = STATIC_DIR / "campus_data.json"
        if not path.exists():
            return None
        with path.open() as fh:
            _campus_cache = json.load(fh)
    return _campus_cache


@app.get("/campuses/texas", tags=["Statewide"])
async def get_texas_campuses():
    """What the district rating hides.

    Every other figure on this site is measured at the district, because that is
    where money is reported. It is the wrong unit for the question a family
    asks: a district rating is an average over campuses, and an average hides
    its own tails.

    **138,664 Texas students attend a campus the state rates D or F inside a
    district the state rates A or B** — 221 campuses across 73 districts, with
    21,415 of those students at a campus rated F.

    And the spread is the rule: **779 of the 890 districts** with more than one
    rated campus contain campuses at different letter grades, and 196 span three
    or more. "The district is a B" is true and describes almost nobody's school.

    Three refusals are carried in the payload. "Not Rated" is not a bad rating
    and its 525 campuses are excluded rather than counted as failure.
    Alternative-education campuses are rated on a different scale and are
    excluded from the headline, with the including-them figure published beside
    it. And no campus is ranked against a campus in another district — the claim
    is about the gap INSIDE a district, which is what a district rating conceals.

    None of this is an accusation: a large district containing a struggling
    campus is arithmetic, not misconduct. Serves with no database.
    """
    data = _campuses()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Campus data not built. Run scripts/ingest_tea_accountability.py "
                   "then scripts/build_campus_data.py")
    return {"meta": data["meta"], **data["texas"]}


@app.get("/district/{district_number}/campuses", tags=["Districts"])
async def get_district_campuses(district_number: str):
    """Every rated campus in one district, worst first, against the district's
    own rating.

    A district with no rated campus returns an `absence` saying which of the two
    reasons applies rather than an empty list.
    """
    data = _campuses()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Campus data not built. Run scripts/ingest_tea_accountability.py "
                   "then scripts/build_campus_data.py")
    rec = data["districts"].get(district_number)
    if rec is None:
        name = _district_name(district_number) or district_number
        return {"district_number": district_number, "district_name": name,
                "meta": data["meta"],
                "absence": absences.no_campus_ratings(name)}
    return {"district_number": district_number, "meta": data["meta"], **rec}


@app.get("/provenance", tags=["General"])
async def get_provenance():
    """Where every number came from, and how to check it yourself.

    "Is this accurate?" is not answerable by asserting yes. It is answerable by
    naming the government file a figure came from, the exact column, the
    arithmetic, and the download link for the original — so a sceptic can redo
    it and disagree.

    Returns the upstream sources (publisher, product, URL, coverage, what each
    is authoritative for), every published measure tied to its source and to
    the test that re-derives it from that source rather than from our own
    output, the steps to verify the whole thing, and what none of it can
    establish. Serves with no database.
    """
    return {
        "site": sources.SITE,
        "sources": sources.SOURCES,
        "measures": sources.MEASURES,
        "how_to_verify": sources.HOW_TO_VERIFY,
        "limits": sources.LIMITS,
        "source_fingerprint": _source_fingerprint(),
    }


def _source_fingerprint() -> Dict[str, Any]:
    """The SHA-256 of the financial file every headline is built from, frozen
    at build time. If the state restates a year, this stops matching and the
    provenance tests fail rather than the change being absorbed silently."""
    path = STATIC_DIR / "source_fingerprint.json"
    if not path.exists():
        return {}
    try:
        with path.open() as fh:
            meta = json.load(fh)
    except Exception:
        return {}
    return {k: meta[k] for k in
            ("source", "source_sha256", "source_bytes", "rows", "districts",
             "first_year", "last_year") if k in meta}


@app.get("/sources", include_in_schema=False)
async def sources_page():
    """The source-of-truth page: every dataset, every measure, and the four
    commands that let anyone check the whole site against the state's files."""
    page = STATIC_DIR / "sources.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Sources page not available")


@app.get("/transparency", include_in_schema=False)
async def transparency_page():
    """AI disclosure, terms of use, and the making-of — linked from the
    disclosure line every page and every outreach email carries. Truth
    head-on: what AI did, what is verified, what can still be wrong, and how
    a reader can check the whole thing independently."""
    page = STATIC_DIR / "transparency.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Transparency page not available")


@app.get("/forensics", include_in_schema=False)
async def forensics_page():
    """The Forensic File: what sits outside the operating total, who pays, what
    the ballot promised, and where it landed — statewide and district by
    district."""
    page = STATIC_DIR / "forensics.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Forensic file not available")


@app.get("/about", include_in_schema=False)
async def about_page():
    """The mission: what this is, why it was built, who it's for, and what we
    stand for — plain-English context for a first-time visitor."""
    page = STATIC_DIR / "about.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="About page not available")


@app.get("/heatmap", include_in_schema=False)
async def heatmap_page():
    """Mapbox choropleth: districts colored by news intensity or outcomes."""
    page = STATIC_DIR / "heatmap.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Heatmap not available")


@app.get("/mapbox-token", include_in_schema=False)
async def mapbox_token():
    """The PUBLIC Mapbox token, from the MAPBOX_TOKEN env var.

    Served from the environment, never committed, so it rotates without a code
    change and never sits in git history. This is the publishable `pk.` token —
    the only kind a browser map needs. The secret `sk.` token must never be
    used here or anywhere client-facing. Returns an empty string when unset, and
    the page shows a configure-me message rather than breaking.
    """
    return {"token": os.getenv("MAPBOX_TOKEN", "")}


@app.get("/map", include_in_schema=False)
async def similarity_map():
    """Serve the statewide similarity map page."""
    page = STATIC_DIR / "map.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Map not available")


@app.get("/geomap", include_in_schema=False)
async def geomap_page():
    """The real geographic map of Texas school district boundaries."""
    page = STATIC_DIR / "geomap.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Map not available")


@app.get("/district-geo", tags=["Districts"])
async def district_geo():
    """Simplified Texas school-district boundaries (Census TIGER 2024, public
    domain) joined to TEA district numbers, with the headline measures merged
    in. Charter districts are absent — they have no geographic boundary."""
    data = STATIC_DIR / "district_geo.json"
    if data.exists():
        return FileResponse(data, media_type="application/json")
    raise HTTPException(status_code=404,
                        detail="Boundary data not built. Run scripts/build_district_geo.py")


@app.get("/fallback-index", tags=["General"])
async def fallback_index():
    """The district picker and statewide figures, with no database involved.

    Fourteen endpoints here are pure static JSON and survive a database outage
    untouched. The front door did not: the page awaited /stats and /benchmarks
    before rendering, and the search box called /districts, so a paused
    Supabase free tier turned a working site into a blank one — including the
    sections that were still perfectly healthy.

    The page falls back to this and keeps going, labelling the statewide
    figures as a snapshot. Built by scripts/build_fallback_index.py.
    """
    data = STATIC_DIR / "fallback_index.json"
    if data.exists():
        return FileResponse(data, media_type="application/json")
    raise HTTPException(status_code=404,
                        detail="Fallback index not built. Run scripts/build_fallback_index.py")


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


# --- Texas ISD Intelligence: daily research → resolve → compare → briefing ---
# The pipeline is in scripts/isd_intel.py (importable, offline-testable, no LLM
# by default). Two endpoints: a secured cron trigger, and a public read.

@app.get("/briefing", tags=["Intelligence"])
async def get_briefing(request: Request):
    """The most recent daily ISD intelligence briefing.

    Reads from the isd_briefings table when a database is configured, and falls
    back to a committed snapshot (static/isd_briefing.json) so the page works
    with no database at all — the same Tier-1 principle as the rest of the site.
    """
    pool = request.app.state.db_pool
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT payload FROM public.isd_briefings ORDER BY run_date DESC LIMIT 1")
                if row:
                    return json.loads(row["payload"])
        except Exception as exc:  # table missing or DB down → fall through to file
            print(f"WARNING: briefing table unavailable, using snapshot: {exc}")
    snap = STATIC_DIR / "isd_briefing.json"
    if snap.exists():
        return FileResponse(snap, media_type="application/json")
    raise HTTPException(status_code=404,
                        detail="No briefing yet. Run the daily research (see docs/ISD_INTELLIGENCE.md).")


async def _record_cron_run(pool, job: str, started: float, status: str,
                           rows_written: int = 0, detail: str = None) -> None:
    """Write one breadcrumb saying this job fired, and what came of it.

    Fails open, deliberately and loudly-in-the-logs-only: a missing table must
    never turn a working pipeline into a 500. The whole point of this record is
    to make failures visible, so it cannot itself become one.

    `detail` is truncated hard. Exception text from asyncpg can contain the
    connection string, and this table is world-readable.
    """
    if pool is None:
        return
    from datetime import timedelta, timezone
    elapsed_ms = int((time.monotonic() - started) * 1000)
    began = datetime.now(timezone.utc) - timedelta(milliseconds=elapsed_ms)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.cron_runs "
                "(job, started_at, duration_ms, status, rows_written, detail) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                job, began, elapsed_ms, status, rows_written,
                (detail or "")[:500] or None)
    except Exception as exc:
        print(f"WARNING: could not record cron run (table missing?): {exc}")


@app.get("/api/cron/runs", tags=["Intelligence"])
async def get_cron_runs(request: Request, job: str = "isd-intelligence",
                        limit: int = 30):
    """Has the scheduled work actually been running?

    A job that never fires and a job that fires and writes nothing look
    identical from outside — which is how the daily intelligence run failed
    silently for four days, with a briefing that simply stopped changing.

    This reports the firings themselves, so **absence is visible**: `gap_days`
    counts the days since the last successful run, and `wrote_nothing` counts
    runs that reported success while producing zero rows, which is the exact
    shape the original failure took. No request data, no identifiers — one row
    per firing and nothing else.
    """
    pool = request.app.state.db_pool
    if pool is None:
        return {"job": job, "available": False,
                "why": "No database configured, so firings are not recorded."}
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT started_at, duration_ms, status, rows_written, detail "
                "FROM public.cron_runs WHERE job = $1 "
                "ORDER BY started_at DESC LIMIT $2",
                job, max(1, min(int(limit), 200)))
    except Exception as exc:
        return {"job": job, "available": False,
                "why": f"cron_runs table not readable — apply "
                       f"sql/create_cron_runs.sql ({type(exc).__name__})"}

    from datetime import timezone
    runs = [dict(r) for r in rows]
    ok = [r for r in runs if r["status"] == "ok"]
    last_ok = ok[0]["started_at"] if ok else None
    gap = ((datetime.now(timezone.utc) - last_ok).days
           if last_ok is not None else None)
    return {
        "job": job,
        "available": True,
        "runs": [{**r, "started_at": r["started_at"].isoformat()} for r in runs],
        "last_success": last_ok.isoformat() if last_ok else None,
        "gap_days": gap,
        "wrote_nothing": sum(1 for r in ok if r["rows_written"] == 0),
        "errors": sum(1 for r in runs if r["status"] == "error"),
        "reading": (
            "gap_days above 1 means the job has not completed since then. "
            "wrote_nothing counts runs that succeeded and produced nothing, "
            "which is what a silent failure looks like from the inside."),
    }


@app.get("/api/cron/isd-intelligence", include_in_schema=False)
async def cron_isd_intelligence(request: Request):
    """Daily research run, triggered by Vercel Cron.

    Vercel Cron issues a GET and auto-injects `Authorization: Bearer
    $CRON_SECRET` when that env var is set — hence GET, not POST. Secured with
    CRON_SECRET and idempotent by date: a second call on the same UTC day
    returns the already-stored run instead of doing the work (and spending)
    twice.
    """
    secret = os.getenv("CRON_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="CRON_SECRET not configured.")
    import secrets as _secrets
    provided = request.headers.get("authorization") or ""
    if not _secrets.compare_digest(provided, f"Bearer {secret}"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from datetime import timezone
    # asyncpg binds a `date` column from a datetime.date, NOT a string — passing
    # the isoformat string raises "'str' object has no attribute 'toordinal'"
    # and the idempotency check + INSERT both fail silently. Keep the date object
    # for the DB and the string for the JSON payload / response.
    run_dt = datetime.now(timezone.utc).date()
    run_date = run_dt.isoformat()
    pool = request.app.state.db_pool
    started = time.monotonic()

    # Idempotency: if today's run already exists, do not re-run.
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                existing = await conn.fetchval(
                    "SELECT 1 FROM public.isd_briefings WHERE run_date = $1", run_dt)
                if existing:
                    # A real outcome, not a failure: this endpoint is idempotent
                    # by date and Vercel can retry. Recorded as its own status so
                    # that a run of nothing but skips is still visibly a run.
                    await _record_cron_run(pool, "isd-intelligence", started,
                                           "skipped", 0, "already ran today")
                    return {"status": "already_ran", "run_date": run_date}
        except Exception as exc:
            print(f"WARNING: idempotency check failed, proceeding: {exc}")

    # The research itself is synchronous and network-bound; keep it off the loop.
    from scripts import isd_intel

    def _run() -> dict:
        districts = isd_intel.load_districts()
        ref = isd_intel.load_reference()
        # Priority districts only, to bound cost and time — the spec's own rule.
        # Statewide queries (incl. an official site:tea.texas.gov query) plus a
        # configurable priority-district list.
        priority = os.getenv(
            "ISD_PRIORITY_DISTRICTS",
            "Beaumont ISD;Fort Worth ISD;Lake Worth ISD;Connally ISD;Houston ISD"
        ).split(";")
        items: list = []
        # Official first: TEA's own newsroom, first-hand and tier-1. This is
        # where a takeover or board-of-managers appointment appears before any
        # paper covers it.
        try:
            items += isd_intel.fetch_tea_newsroom()
        except Exception as exc:
            print(f"WARNING: TEA newsroom fetch failed: {exc}")
        # Then Google News for breadth across the priority districts.
        queries = isd_intel.build_queries(None)
        for name in priority:
            queries += isd_intel.build_queries(name.strip())
        for q in queries[: int(os.getenv("ISD_MAX_QUERIES", "12"))]:
            try:
                items += isd_intel.fetch_google_news_rss(q)
            except Exception as exc:  # one bad feed must not sink the run
                print(f"WARNING: feed failed for {q!r}: {exc}")

        # LLM enrichment is opt-in and hard-bounded. Off unless ISD_LLM_EXTRACT
        # is set AND a key is present; capped at ISD_LLM_MAX_CALLS per run so it
        # cannot become a surprise bill — the same discipline as the /query cap.
        enrich = None
        if os.getenv("ISD_LLM_EXTRACT") == "1" and llm_config.resolve_llm_config().configured:
            budget = isd_intel.LlmBudget(int(os.getenv("ISD_LLM_MAX_CALLS", "25")))
            client = isd_intel.make_openai_client()
            enrich = lambda it: isd_intel.extract_with_llm(it, client, budget)  # noqa: E731

        findings = isd_intel.analyze(items, districts, ref, enrich=enrich)
        return isd_intel.build_briefing(findings, run_date)

    try:
        briefing = await run_in_threadpool(_run)
    except Exception as exc:
        # Record BEFORE re-raising. Previously this path left nothing behind, so
        # a job failing every day was indistinguishable from a job that was
        # never scheduled.
        await _record_cron_run(pool, "isd-intelligence", started, "error", 0,
                               f"{type(exc).__name__}: {exc}")
        raise

    stored = False
    store_error = None
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO public.isd_briefings (run_date, payload) VALUES ($1, $2) "
                    "ON CONFLICT (run_date) DO UPDATE SET payload = EXCLUDED.payload",
                    run_dt, json.dumps(briefing))
                stored = True
        except Exception as exc:
            print(f"WARNING: could not store briefing (table missing?): {exc}")
            store_error = f"{type(exc).__name__}: {exc}"

    # rows_written is what makes the original failure legible after the fact:
    # the run succeeded, analysed items, and persisted nothing. Recording a
    # bare "ok" would have hidden it exactly as before.
    await _record_cron_run(
        pool, "isd-intelligence", started,
        "ok" if stored else "error",
        briefing["meta"]["items_analyzed"] if stored else 0,
        None if stored else (store_error or "briefing built but not persisted"))

    return {"status": "ok", "run_date": run_date, "stored": stored,
            "items_analyzed": briefing["meta"]["items_analyzed"],
            "review_items": briefing["meta"]["review_items"]}


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
    """Health check endpoint.

    Reports which language-model provider is actually live, so a provider
    switch can be confirmed from outside without reading env vars. `llm` is a
    key-free description (provider:model via host) — never the API key itself.
    """
    llm = llm_config.describe()
    pool = request.app.state.db_pool
    # Whether the journey-tracking tables exist. Without this, a deploy where
    # the migration failed looks identical from outside to one where it worked
    # — and the symptom (clicks silently dropped) is invisible by design,
    # because a foreign-key rejection is caught and logged, not surfaced.
    schema = getattr(request.app.state, "schema_status", "unknown")
    if pool is None:
        return {"status": "degraded", "database": "not configured", "llm": llm,
                "tracking_schema": schema}
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected", "llm": llm,
                "tracking_schema": schema}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# Run with: uvicorn src.api:app --reload --port 8000

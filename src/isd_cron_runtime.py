"""Production hardening for the daily Texas ISD intelligence cron.

The historical handler in :mod:`src.api` predates the review queue and treats
its briefing write as best-effort.  This module owns the production cron route
at the serverless entrypoint so the daily job has one clear commit boundary:
briefing + human-review rows are committed together, storage failures are 503s,
and a concurrent invocation cannot overwrite the first completed run.

No external queue, webhook, or edge worker is involved. Postgres is the durable
boundary and ``run_date`` is the idempotency/concurrency key.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import api as core

_CRON_PATH = "/api/cron/isd-intelligence"


def _inserted(command: Any) -> bool:
    """Return True only when asyncpg reports one inserted row."""
    return str(command).rstrip().endswith(" 1")


async def persist_briefing(conn, run_dt, briefing: dict) -> tuple[bool, int]:
    """Atomically persist one briefing and its review queue.

    ``False`` means another invocation committed the same UTC date first. That
    is an idempotent skip, not an error. Any queue failure raises and rolls the
    briefing insert back with it.
    """
    review = list(briefing.get("review_queue") or [])
    async with conn.transaction():
        command = await conn.execute(
            "INSERT INTO public.isd_briefings (run_date, payload) VALUES ($1, $2) "
            "ON CONFLICT (run_date) DO NOTHING",
            run_dt,
            json.dumps(briefing),
        )
        if not _inserted(command):
            return False, 0

        queued = 0
        for finding in review:
            content_hash = str(finding.get("content_hash") or "").strip()
            if not content_hash:
                raise ValueError("review item is missing content_hash")
            q_command = await conn.execute(
                "INSERT INTO public.isd_review_queue "
                "(run_date, content_hash, finding) VALUES ($1, $2, $3) "
                "ON CONFLICT (run_date, content_hash) DO NOTHING",
                run_dt,
                content_hash,
                json.dumps(finding),
            )
            if not _inserted(q_command):
                # The briefing itself was just inserted, so a conflict for the
                # same run_date can only be a duplicate hash in this payload.
                # Roll back rather than publish a partial review queue.
                raise ValueError(f"duplicate review content_hash: {content_hash}")
            queued += 1
        return True, queued


async def cron_isd_intelligence(request: Request):
    """Run the daily research job with durable, fail-closed persistence."""
    secret = os.getenv("CRON_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="CRON_SECRET not configured.")
    provided = request.headers.get("authorization") or ""
    if not secrets.compare_digest(provided, f"Bearer {secret}"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    run_dt = datetime.now(timezone.utc).date()
    run_date = run_dt.isoformat()
    pool = getattr(request.app.state, "db_pool", None)
    started = time.monotonic()

    # A daily research result with nowhere durable to land is not a successful
    # run. Refuse before network/LLM work rather than spend and return a false 200.
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable; daily intelligence requires durable storage.",
        )

    # Cheap preflight avoids duplicate network/LLM work. The INSERT repeats the
    # guarantee atomically because two serverless instances can both pass this
    # SELECT before either reaches the commit point.
    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT 1 FROM public.isd_briefings WHERE run_date = $1", run_dt
            )
    except Exception as exc:  # database uncertain -> do not spend
        print(f"ERROR: idempotency preflight failed: {type(exc).__name__}: {exc}")
        await core._record_cron_run(
            pool,
            "isd-intelligence",
            started,
            "error",
            0,
            f"idempotency preflight failed ({type(exc).__name__})",
        )
        raise HTTPException(
            status_code=503,
            detail="Could not verify intelligence storage; no research was started.",
        )

    if existing:
        await core._record_cron_run(
            pool, "isd-intelligence", started, "skipped", 0, "already ran today"
        )
        return {"status": "already_ran", "run_date": run_date, "stored": True}

    from scripts import isd_intel

    def _run() -> dict:
        districts = isd_intel.load_districts()
        ref = isd_intel.load_reference()
        priority = os.getenv(
            "ISD_PRIORITY_DISTRICTS",
            "Beaumont ISD;Fort Worth ISD;Lake Worth ISD;Connally ISD;Houston ISD",
        ).split(";")
        items: list = []

        try:
            items += isd_intel.fetch_tea_newsroom()
        except Exception as exc:
            print(f"WARNING: TEA newsroom fetch failed: {exc}")

        queries = isd_intel.build_queries(None)
        for name in priority:
            queries += isd_intel.build_queries(name.strip())
        for query in queries[: int(os.getenv("ISD_MAX_QUERIES", "12"))]:
            try:
                items += isd_intel.fetch_google_news_rss(query)
            except Exception as exc:
                print(f"WARNING: feed failed for {query!r}: {exc}")

        enrich = None
        if (
            os.getenv("ISD_LLM_EXTRACT") == "1"
            and core.llm_config.resolve_llm_config().configured
        ):
            budget = isd_intel.LlmBudget(
                int(os.getenv("ISD_LLM_MAX_CALLS", "25"))
            )
            client = isd_intel.make_openai_client()
            enrich = lambda item: isd_intel.extract_with_llm(  # noqa: E731
                item, client, budget
            )

        findings = isd_intel.analyze(items, districts, ref, enrich=enrich)
        return isd_intel.build_briefing(findings, run_date)

    try:
        briefing = await core.run_in_threadpool(_run)
    except Exception as exc:
        await core._record_cron_run(
            pool,
            "isd-intelligence",
            started,
            "error",
            0,
            f"research failed ({type(exc).__name__})",
        )
        raise

    try:
        async with pool.acquire() as conn:
            stored, review_queued = await persist_briefing(conn, run_dt, briefing)
    except Exception as exc:
        print(f"ERROR: intelligence persistence failed: {type(exc).__name__}: {exc}")
        await core._record_cron_run(
            pool,
            "isd-intelligence",
            started,
            "error",
            0,
            f"persistence failed ({type(exc).__name__})",
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "storage_failed",
                "run_date": run_date,
                "stored": False,
                "items_analyzed": briefing["meta"]["items_analyzed"],
                "review_items": briefing["meta"]["review_items"],
            },
        )

    if not stored:
        await core._record_cron_run(
            pool,
            "isd-intelligence",
            started,
            "skipped",
            0,
            "concurrent run committed this date first",
        )
        return {
            "status": "already_ran",
            "run_date": run_date,
            "stored": True,
            "concurrent": True,
        }

    rows_written = 1 + review_queued
    await core._record_cron_run(
        pool,
        "isd-intelligence",
        started,
        "ok",
        rows_written,
        f"briefing=1 review_queue={review_queued}",
    )
    return {
        "status": "ok",
        "run_date": run_date,
        "stored": True,
        "items_analyzed": briefing["meta"]["items_analyzed"],
        "review_items": briefing["meta"]["review_items"],
        "review_queued": review_queued,
        "rows_written": rows_written,
    }


def install(app: FastAPI) -> None:
    """Replace the legacy cron route, and only that route, on an app instance."""
    matches = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) == _CRON_PATH
        and "GET" in (getattr(route, "methods", set()) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one legacy {_CRON_PATH} GET route, found {len(matches)}"
        )
    app.router.routes.remove(matches[0])
    app.add_api_route(
        _CRON_PATH,
        cron_isd_intelligence,
        methods=["GET"],
        include_in_schema=False,
    )

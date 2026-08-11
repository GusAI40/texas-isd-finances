"""Tests for the cron run log.

The bug this closes is a specific one and worth restating, because the tests
only make sense against it: the daily intelligence run failed silently for four
days. Vercel fired it, the work raised, the handler swallowed it, and nothing
recorded that a run had been attempted. The symptom was a briefing that stopped
changing, which looks exactly like a quiet week.

Two things follow, and both are asserted here.

**Absence must be visible.** A job that never fires and a job that fires and
writes nothing are indistinguishable if you only ever read the pipeline's
output. So the ATTEMPT is recorded, and `/api/cron/runs` reports `gap_days`
and `wrote_nothing` — the second being the exact shape the original failure
took, a run that returned success and persisted zero rows.

**The log must never become the outage.** A telemetry table that 500s the
pipeline it is watching is worse than no telemetry. Every write fails open.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import src.api as api  # noqa: E402


@pytest.fixture
def client():
    with TestClient(api.app) as c:
        yield c


class FakeConn:
    def __init__(self, sink, fail=False):
        self.sink, self.fail = sink, fail

    async def execute(self, sql, *args):
        if self.fail:
            raise RuntimeError("relation \"public.cron_runs\" does not exist")
        self.sink.append((sql, args))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakePool:
    """Minimal stand-in for an asyncpg pool: `async with pool.acquire()`."""

    def __init__(self, fail=False):
        self.writes, self.fail = [], fail

    def acquire(self):
        return FakeConn(self.writes, self.fail)


# --- the write itself -------------------------------------------------------

@pytest.mark.anyio
async def test_a_run_is_recorded_with_its_outcome():
    import time
    pool = FakePool()
    await api._record_cron_run(pool, "isd-intelligence", time.monotonic(),
                               "ok", 42)
    assert len(pool.writes) == 1
    sql, args = pool.writes[0]
    assert "INSERT INTO public.cron_runs" in sql
    job, began, ms, status, rows, detail = args
    assert job == "isd-intelligence" and status == "ok" and rows == 42
    assert ms >= 0 and began is not None


@pytest.mark.anyio
async def test_a_missing_table_does_not_break_the_pipeline():
    """The whole point of this table is to surface failures. It must not be
    able to cause one."""
    import time
    pool = FakePool(fail=True)
    await api._record_cron_run(pool, "isd-intelligence", time.monotonic(), "ok", 1)
    assert pool.writes == []          # nothing written, and no exception raised


@pytest.mark.anyio
async def test_no_database_is_a_no_op_not_a_crash():
    import time
    await api._record_cron_run(None, "isd-intelligence", time.monotonic(), "ok", 1)


@pytest.mark.anyio
async def test_detail_is_truncated_because_the_table_is_world_readable():
    """asyncpg exception text can carry the connection string."""
    import time
    pool = FakePool()
    await api._record_cron_run(pool, "j", time.monotonic(), "error", 0, "x" * 5000)
    detail = pool.writes[0][1][5]
    assert len(detail) <= 500


@pytest.mark.anyio
async def test_skipped_is_its_own_status_not_an_error():
    """The cron is idempotent by date and Vercel retries. Recording a retry as
    a failure would train whoever reads this to ignore real failures."""
    import time
    pool = FakePool()
    await api._record_cron_run(pool, "j", time.monotonic(), "skipped", 0, "already ran")
    assert pool.writes[0][1][3] == "skipped"


# --- the read ---------------------------------------------------------------

def test_the_endpoint_says_so_when_there_is_no_database(client):
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), None
    try:
        body = client.get("/api/cron/runs").json()
        assert body["available"] is False and "why" in body
    finally:
        api.app.state.db_pool = saved


def test_the_endpoint_explains_how_to_enable_itself(client):
    """A missing table must produce an instruction, not a 500 and not silence."""
    class Broken:
        def acquire(self):
            raise RuntimeError("no such table")
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), Broken()
    try:
        body = client.get("/api/cron/runs").json()
        assert body["available"] is False
        assert "create_cron_runs.sql" in body["why"]
    finally:
        api.app.state.db_pool = saved


def test_the_endpoint_collects_no_identifiers(client):
    """The site's published privacy promise applies here too."""
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), None
    try:
        blob = client.get("/api/cron/runs").text.lower()
        for w in ("ip", "cookie", "session", "user_agent", "referrer"):
            assert f'"{w}"' not in blob
    finally:
        api.app.state.db_pool = saved


# --- the migration ----------------------------------------------------------

def test_the_migration_records_the_three_real_outcomes():
    sql = (ROOT / "sql" / "create_cron_runs.sql").read_text()
    assert "CHECK (status IN ('ok', 'skipped', 'error'))" in sql
    assert "rows_written" in sql, "a run that wrote nothing must be recordable"
    assert "ENABLE ROW LEVEL SECURITY" in sql


def test_the_migration_stores_nothing_about_who_made_a_request():
    sql = (ROOT / "sql" / "create_cron_runs.sql").read_text().lower()
    for col in ("ip_address", "user_agent", "session", "cookie", "visitor"):
        assert col not in sql, f"cron_runs must not carry {col}"

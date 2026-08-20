"""Regression tests for the hardened daily ISD intelligence runtime.

These tests use no database, network, or LLM. They pin the operational contract:
briefing + review rows commit together, storage failure is not a false 200, and
a concurrent serverless invocation loses cleanly at the database boundary.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts import isd_intel
from src import isd_cron_runtime as runtime


class _Tx:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        self.store["tx_entered"] = self.store.get("tx_entered", 0) + 1
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        key = "tx_rolled_back" if exc_type else "tx_committed"
        self.store[key] = self.store.get(key, 0) + 1
        return False


class _Conn:
    def __init__(self, store, *, existing=False, race=False, fail_review=False):
        self.store = store
        self.existing = existing
        self.race = race
        self.fail_review = fail_review

    def transaction(self):
        return _Tx(self.store)

    async def fetchval(self, sql, *args):
        self.store.setdefault("fetchvals", []).append((sql, args))
        if "isd_briefings" in sql:
            return 1 if self.existing else None
        return 1

    async def execute(self, sql, *args):
        self.store.setdefault("executed", []).append((sql, args))
        if "isd_briefings" in sql:
            return "INSERT 0 0" if self.race else "INSERT 0 1"
        if "isd_review_queue" in sql:
            if self.fail_review:
                raise RuntimeError("queue insert failed")
            return "INSERT 0 1"
        if "cron_runs" in sql:
            return "INSERT 0 1"
        return "INSERT 0 1"


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Pool:
    def __init__(self, *, existing=False, race=False, fail_review=False):
        self.store = {}
        self.conn = _Conn(
            self.store,
            existing=existing,
            race=race,
            fail_review=fail_review,
        )

    def acquire(self):
        return _Acquire(self.conn)


BRIEFING = {
    "meta": {"items_analyzed": 7, "review_items": 1},
    "top_findings": [],
    "review_queue": [
        {
            "content_hash": "abc123",
            "headline": "Needs human review",
            "review_required": True,
        }
    ],
}


def _app(pool):
    app = FastAPI()

    @app.get(runtime._CRON_PATH, include_in_schema=False)
    async def legacy():
        return {"legacy": True}

    runtime.install(app)
    app.state.db_pool = pool
    return app


def _wire_research(monkeypatch, *, on_load=None):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setenv("ISD_LLM_EXTRACT", "0")

    def load_districts():
        if on_load:
            on_load()
        return []

    monkeypatch.setattr(isd_intel, "load_districts", load_districts)
    monkeypatch.setattr(isd_intel, "load_reference", lambda: {})
    monkeypatch.setattr(isd_intel, "fetch_tea_newsroom", lambda: [])
    monkeypatch.setattr(isd_intel, "build_queries", lambda _name: [])
    monkeypatch.setattr(isd_intel, "fetch_google_news_rss", lambda _query: [])
    monkeypatch.setattr(isd_intel, "analyze", lambda *_a, **_k: [])
    monkeypatch.setattr(isd_intel, "build_briefing", lambda *_a, **_k: BRIEFING)


def _call(app):
    with TestClient(app) as client:
        return client.get(
            runtime._CRON_PATH,
            headers={"authorization": "Bearer s3cret"},
        )


def test_success_commits_briefing_and_review_queue_together(monkeypatch):
    _wire_research(monkeypatch)
    pool = _Pool()

    res = _call(_app(pool))

    assert res.status_code == 200
    assert res.json()["stored"] is True
    assert res.json()["review_queued"] == 1
    assert res.json()["rows_written"] == 2
    assert pool.store.get("tx_committed") == 1
    assert not pool.store.get("tx_rolled_back")

    writes = pool.store["executed"]
    assert any("isd_briefings" in sql for sql, _ in writes)
    assert any("isd_review_queue" in sql for sql, _ in writes)
    run = next(args for sql, args in writes if "cron_runs" in sql)
    assert run[3] == "ok"
    assert run[4] == 2
    assert "review_queue=1" in run[5]


def test_review_failure_rolls_back_and_returns_503(monkeypatch):
    _wire_research(monkeypatch)
    pool = _Pool(fail_review=True)

    res = _call(_app(pool))

    assert res.status_code == 503
    assert res.json()["status"] == "storage_failed"
    assert res.json()["stored"] is False
    assert pool.store.get("tx_rolled_back") == 1
    assert not pool.store.get("tx_committed")
    run = next(args for sql, args in pool.store["executed"] if "cron_runs" in sql)
    assert run[3] == "error"
    assert run[4] == 0


def test_concurrent_loser_skips_without_queue_writes(monkeypatch):
    _wire_research(monkeypatch)
    pool = _Pool(race=True)

    res = _call(_app(pool))

    assert res.status_code == 200
    assert res.json()["status"] == "already_ran"
    assert res.json()["concurrent"] is True
    assert res.json()["stored"] is True
    assert pool.store.get("tx_committed") == 1
    writes = pool.store["executed"]
    assert not any("isd_review_queue" in sql for sql, _ in writes)
    run = next(args for sql, args in writes if "cron_runs" in sql)
    assert run[3] == "skipped"


def test_missing_database_refuses_before_research(monkeypatch):
    calls = {"load": 0}
    _wire_research(
        monkeypatch,
        on_load=lambda: calls.__setitem__("load", calls["load"] + 1),
    )

    res = _call(_app(None))

    assert res.status_code == 503
    assert "durable storage" in res.json()["detail"]
    assert calls["load"] == 0


def test_existing_run_skips_before_research(monkeypatch):
    calls = {"load": 0}
    _wire_research(
        monkeypatch,
        on_load=lambda: calls.__setitem__("load", calls["load"] + 1),
    )
    pool = _Pool(existing=True)

    res = _call(_app(pool))

    assert res.status_code == 200
    assert res.json()["status"] == "already_ran"
    assert res.json()["stored"] is True
    assert calls["load"] == 0


def test_hardened_route_stays_out_of_openapi(monkeypatch):
    _wire_research(monkeypatch)
    app = _app(_Pool(existing=True))
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert runtime._CRON_PATH not in paths

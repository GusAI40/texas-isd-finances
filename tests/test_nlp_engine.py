"""Construction tests for the NLP engine against a local SQLite database.

These exist to catch LangChain API drift: the engine must import and
construct against the installed library versions without any network access.
"""
import re
import sqlite3
from pathlib import Path

import pytest

from src.nlp_engine import SAMPLE_QUERIES, TexasFinanceNLPEngine


@pytest.fixture()
def sqlite_url(tmp_path):
    db_path = tmp_path / "finance.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE v_finance_summary (
            district_number TEXT, district_name TEXT, year INTEGER,
            total_revenue REAL, total_spend REAL, enrollment INTEGER,
            spend_per_student REAL, revenue_per_student REAL,
            instruction_spend REAL, debt_service REAL, capital_projects REAL
        )
    """)
    conn.execute("""
        CREATE TABLE v_anomaly_flags (
            district_number TEXT, district_name TEXT, year INTEGER,
            revenue_drop_flag BOOLEAN, spend_spike_flag BOOLEAN,
            per_student_spike_flag BOOLEAN, enrollment_decline_flag BOOLEAN
        )
    """)
    conn.commit()
    conn.close()
    return f"sqlite:///{db_path}"


def test_engine_constructs_against_installed_langchain(sqlite_url, monkeypatch):
    # SQLite's dialect lacks materialized-view reflection, so inject the
    # SQLDatabase (the Postgres path uses view_support=True in production).
    from langchain_community.utilities import SQLDatabase

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    db = SQLDatabase.from_uri(
        sqlite_url, include_tables=["v_finance_summary", "v_anomaly_flags"]
    )
    engine = TexasFinanceNLPEngine(db=db)
    assert engine.agent is not None
    assert set(engine.db.get_usable_table_names()) == {"v_finance_summary", "v_anomaly_flags"}


def test_engine_requires_db_url(monkeypatch):
    monkeypatch.delenv("NLP_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(ValueError, match="NLP_DB_URL"):
        TexasFinanceNLPEngine()


def test_engine_prefers_least_privilege_url(sqlite_url, monkeypatch):
    """The owner connection must never be used when the reader role exists.

    A language model writes the SQL on this path, so the privilege boundary
    has to live in the database. If this preference ever flips, /query starts
    running model-authored SQL as the table owner.
    """
    from langchain_community.utilities import SQLDatabase

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("NLP_DB_URL", "postgresql://nlp_reader:pw@reader.example:6543/postgres")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://owner:pw@owner.example:6543/postgres")

    # SQLite cannot reflect materialized views, so stand in for the connection
    # and record which URL the engine asked for.
    dialled = {}
    real_from_uri = SQLDatabase.from_uri

    def fake_from_uri(url, **kwargs):
        dialled["url"] = url
        return real_from_uri(
            sqlite_url, include_tables=["v_finance_summary", "v_anomaly_flags"]
        )

    monkeypatch.setattr("src.nlp_engine.SQLDatabase.from_uri", fake_from_uri)
    TexasFinanceNLPEngine()
    assert "nlp_reader" in dialled["url"], "engine reached for the owner connection"


def test_nlp_role_migration_grants_only_the_two_views():
    """sql/create_nlp_role.sql is the enforcement point — assert its shape."""
    sql = Path("sql/create_nlp_role.sql").read_text()
    assert "CREATE ROLE nlp_reader" in sql
    assert "NOSUPERUSER" in sql and "NOCREATEDB" in sql and "NOCREATEROLE" in sql
    assert "default_transaction_read_only = on" in sql
    granted = set(re.findall(r"GRANT SELECT ON public\.(\w+) TO nlp_reader", sql))
    assert granted == {"v_finance_summary", "v_anomaly_flags"}
    assert "CHANGE_ME" in sql, "the password must stay a placeholder, never a real secret"


def test_sample_queries_exposed():
    assert len(SAMPLE_QUERIES) == 10


# --- the /query spend ceiling -------------------------------------------------
# These pin the two failure modes apart. They used to be one branch that failed
# open, which left the bill uncapped during exactly the outage nobody watches.

class _Conn:
    def __init__(self, exc): self.exc = exc
    async def fetchval(self, *a, **k): raise self.exc
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class _Pool:
    def __init__(self, exc): self.exc = exc
    def acquire(self): return _Conn(self.exc)


def test_missing_usage_table_fails_open():
    """A migration that has not run yet must not take down a working feature:
    the database is up, so the agent can still answer."""
    import asyncio

    import asyncpg

    from src.api import _shared_limit_reached
    exc = asyncpg.exceptions.UndefinedTableError("relation does not exist")
    assert asyncio.run(_shared_limit_reached(_Pool(exc))) is False


def test_unreachable_metering_degrades_to_a_trickle():
    """Not open, not shut. Metering can fail while the database is up (pooler
    exhaustion), so refusing everything would break a working feature. But
    failing fully open left the bill unbounded during exactly the outage nobody
    watches. So a degraded instance answers a few and then refuses."""
    import asyncio

    import src.api as api
    api._degraded_hits.clear()
    pool = _Pool(OSError("connection refused"))
    for _ in range(api._DEGRADED_LIMIT):
        assert asyncio.run(api._shared_limit_reached(pool)) is False
    assert asyncio.run(api._shared_limit_reached(pool)) is True
    api._degraded_hits.clear()


def test_no_pool_is_not_a_refusal():
    """No pool configured at all is a local/dev shape, not an outage."""
    import asyncio

    from src.api import _shared_limit_reached
    assert asyncio.run(_shared_limit_reached(None)) is False

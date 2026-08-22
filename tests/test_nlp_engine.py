"""Construction tests for the NLP engine against a local SQLite database.

These exist to catch LangChain API drift: the engine must import and
construct against the installed library versions without any network access.
"""
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.nlp_engine import (
    NLP_RELATIONS,
    SAMPLE_QUERIES,
    FinanceSQLDatabase,
    TexasFinanceNLPEngine,
    _assert_select_only,
    build_sql_tools,
)


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


@pytest.fixture
def no_proxy_env(monkeypatch):
    """Keep client construction independent of the runner's proxy extras."""

    for name in (
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


def test_engine_constructs_against_installed_langchain(
    sqlite_url, monkeypatch, no_proxy_env
):
    # SQLite's dialect lacks materialized-view reflection, so inject the
    # app-owned database adapter (Postgres reflects materialized views too).

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    db = FinanceSQLDatabase.from_uri(sqlite_url)
    engine = TexasFinanceNLPEngine(db=db)
    assert engine.agent is not None
    assert set(engine.db.get_usable_table_names()) == {"v_finance_summary", "v_anomaly_flags"}
    assert {tool.name for tool in engine.tools} == {
        "sql_db_list_tables",
        "sql_db_schema",
        "sql_db_query",
        "sql_db_query_checker",
    }


def test_engine_requires_db_url(monkeypatch):
    monkeypatch.delenv("NLP_DB_URL", raising=False)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://owner-must-not-be-used")
    with pytest.raises(ValueError, match="NLP_DB_URL"):
        TexasFinanceNLPEngine()


def test_query_failure_never_returns_provider_exception_text(capsys):
    sentinel = "postgres://owner:pw@db.example recipient@example.org sk-secret"

    class FailingAgent:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError(sentinel)

    engine = object.__new__(TexasFinanceNLPEngine)
    engine.agent = FailingAgent()
    result = engine.query("Compare district spending")

    assert result == {
        "success": False,
        "error": "The question could not be answered. Please try again.",
        "question": "Compare district spending",
    }
    assert sentinel not in capsys.readouterr().out


def test_engine_prefers_least_privilege_url(
    sqlite_url, monkeypatch, no_proxy_env
):
    """The owner connection must never be used when the reader role exists.

    A language model writes the SQL on this path, so the privilege boundary
    has to live in the database. If this preference ever flips, /query starts
    running model-authored SQL as the table owner.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("NLP_DB_URL", "postgresql://nlp_reader:pw@reader.example:6543/postgres")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://owner:pw@owner.example:6543/postgres")

    # SQLite cannot reflect materialized views, so stand in for the connection
    # and record which URL the engine asked for.
    dialled = {}
    real_from_uri = FinanceSQLDatabase.from_uri

    def fake_from_uri(url, **kwargs):
        dialled["url"] = url
        return real_from_uri(sqlite_url, include_relations=NLP_RELATIONS)

    monkeypatch.setattr(FinanceSQLDatabase, "from_uri", staticmethod(fake_from_uri))
    TexasFinanceNLPEngine()
    assert "nlp_reader" in dialled["url"], "engine reached for the owner connection"


class _CheckerLLM:
    def invoke(self, prompt):
        return type("Message", (), {"text": "SELECT 1"})()


def test_app_owned_sql_tools_are_allowlisted_and_select_only(sqlite_url):
    db = FinanceSQLDatabase.from_uri(sqlite_url)
    tools = {tool.name: tool for tool in build_sql_tools(db, _CheckerLLM())}

    assert tools["sql_db_list_tables"].invoke({}) == (
        "v_anomaly_flags, v_finance_summary"
    )
    assert "RELATION" in tools["sql_db_schema"].invoke(
        {"table_names": "v_finance_summary"}
    )
    assert "not found in database" in tools["sql_db_schema"].invoke(
        {"table_names": "sqlite_master"}
    )
    assert tools["sql_db_query"].invoke(
        {"query": "SELECT COUNT(*) FROM v_finance_summary"}
    ) == "[(0,)]"
    assert "only SELECT" in tools["sql_db_query"].invoke(
        {"query": "DELETE FROM v_finance_summary"}
    )
    assert "rejected keyword: DELETE" in tools["sql_db_query"].invoke(
        {"query": "WITH changed AS (DELETE FROM v_finance_summary RETURNING *) SELECT * FROM changed"}
    )
    assert "one SQL statement" in tools["sql_db_query"].invoke(
        {"query": "SELECT 1; SELECT 2"}
    )


def test_sql_tools_never_return_driver_exception_text(capsys):
    sentinel = "postgres://owner:pw@db.example recipient@example.org sk-secret"

    class FailingDB:
        dialect = "postgresql"

        def get_usable_table_names(self):
            return list(NLP_RELATIONS)

        def get_table_info(self, _names):
            raise RuntimeError(sentinel)

        def run(self, _query):
            raise RuntimeError(sentinel)

    tools = {tool.name: tool for tool in build_sql_tools(FailingDB(), _CheckerLLM())}
    schema_result = tools["sql_db_schema"].invoke(
        {"table_names": "v_finance_summary"})
    query_result = tools["sql_db_query"].invoke(
        {"query": "SELECT 1 FROM v_finance_summary"})

    assert schema_result == "Error: schema lookup failed"
    assert query_result == "Error: query execution failed"
    assert sentinel not in schema_result + query_result + capsys.readouterr().out


def test_select_validator_ignores_keywords_inside_values_and_comments():
    _assert_select_only("SELECT 'delete; update', \"drop\" -- insert\nFROM v_finance_summary")


@pytest.mark.parametrize(
    "query",
    [
        "SELECT pg_advisory_lock(33040433162)",
        "SELECT pg_advisory_xact_lock(33040433162)",
        "SELECT set_config('statement_timeout', '0', false)",
        "SELECT pg_notify('channel', 'payload')",
        "SELECT pg_sleep(10)",
        "SELECT nextval('some_sequence')",
        "SELECT public.abs(-1)",
    ],
)
def test_select_validator_rejects_session_and_side_effect_functions(query):
    with pytest.raises(ValueError, match="(?:function|expression).*not allowed"):
        _assert_select_only(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM texas_school_finance",
        "WITH hidden AS (SELECT * FROM pg_catalog.pg_authid) SELECT * FROM hidden",
        "SELECT * FROM pg_sleep(1)",
    ],
)
def test_select_validator_rejects_every_relation_outside_two_views(query):
    with pytest.raises(ValueError, match="(?:SQL function|relation).*not allowed"):
        _assert_select_only(query)


def test_select_validator_accepts_finance_ctes_and_pure_functions():
    query = (
        "WITH yearly AS ("
        "SELECT district_number, year, ROUND(SUM(total_spend), 2) AS spend "
        "FROM v_finance_summary GROUP BY district_number, year) "
        "SELECT district_number, year, spend, "
        "LAG(spend) OVER (PARTITION BY district_number ORDER BY year) AS prior "
        "FROM yearly ORDER BY district_number, year LIMIT 100"
    )
    assert _assert_select_only(query) == query


def test_select_validator_accepts_normal_predicates_and_case():
    query = (
        "SELECT district_name, "
        "CASE WHEN total_spend > total_revenue OR enrollment < 100 "
        "THEN 'review' ELSE 'ok' END AS flag "
        "FROM v_finance_summary "
        "WHERE year >= 2020 AND year <= 2025"
    )
    assert _assert_select_only(query) == query


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM v_finance_summary TABLESAMPLE SYSTEM (1)",
        "SELECT 1 OPERATOR(pg_catalog.+) 2 FROM v_finance_summary",
    ],
)
def test_select_validator_rejects_unreviewed_sql_surfaces(query):
    with pytest.raises(ValueError, match="SQL expression .* not allowed"):
        _assert_select_only(query)


def test_postgres_execution_qualifies_views_and_rejects_recursive_ctes():
    safe = _assert_select_only(
        "SELECT COUNT(*) FROM v_finance_summary",
        qualify_relations=True,
    )
    assert "public.v_finance_summary" in safe
    with pytest.raises(ValueError, match="recursive CTEs"):
        _assert_select_only(
            "WITH RECURSIVE numbers(n) AS ("
            "SELECT 1 UNION ALL SELECT n + 1 FROM numbers WHERE n < 150) "
            "SELECT n FROM numbers"
        )


def test_database_adapter_bounds_model_visible_rows(sqlite_url):
    db = FinanceSQLDatabase.from_uri(sqlite_url)
    with db._engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO v_finance_summary (year) VALUES (?)",
            [(year,) for year in range(1, 151)],
        )
    output = db.run("SELECT year FROM v_finance_summary ORDER BY year")
    assert "(100,)" in output
    assert "(101,)" not in output
    assert "Result truncated after 100 rows" in output


def test_query_normalizes_structured_provider_content():
    class StructuredAgent:
        def invoke(self, *args, **kwargs):
            message = type(
                "Message",
                (),
                {"content": [{"type": "text", "text": "**Answer:** 42"}]},
            )()
            return {"messages": [message]}

    engine = object.__new__(TexasFinanceNLPEngine)
    engine.agent = StructuredAgent()
    result = engine.query("How many?")
    assert result["success"] is True
    assert result["answer"] == "**Answer:** 42"


def test_runtime_no_longer_depends_on_archived_langchain_community():
    root = Path(__file__).resolve().parent.parent
    source = (root / "src" / "nlp_engine.py").read_text()
    manifests = [
        root / "pyproject.toml",
        root / "requirements.txt",
    ]
    assert "from langchain_community" not in source
    assert "import langchain_community" not in source
    assert all("langchain-community" not in path.read_text() for path in manifests)

    # Prove a clean interpreter can import the runtime while actively refusing
    # the archived package. This catches indirect imports that source greps miss.
    probe = r"""
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "langchain_community" or name.startswith("langchain_community."):
        raise AssertionError(f"archived package imported: {name}")
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
import src.nlp_engine
"""
    subprocess.run([sys.executable, "-c", probe], cwd=root, check=True)


def test_nlp_role_migration_grants_only_the_two_views():
    """sql/create_nlp_role.sql is the enforcement point — assert its shape."""
    sql = Path("sql/create_nlp_role.sql").read_text()
    assert "CREATE ROLE nlp_reader" in sql
    assert "NOSUPERUSER" in sql and "NOCREATEDB" in sql and "NOCREATEROLE" in sql
    assert "default_transaction_read_only = on" in sql
    assert "search_path = pg_catalog" in sql
    assert "falls back to SUPABASE_DB_URL" not in sql
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

"""Construction tests for the NLP engine against a local SQLite database.

These exist to catch LangChain API drift: the engine must import and
construct against the installed library versions without any network access.
"""
import sqlite3

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
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(ValueError, match="SUPABASE_DB_URL"):
        TexasFinanceNLPEngine()


def test_sample_queries_exposed():
    assert len(SAMPLE_QUERIES) == 10

"""The self-applying schema, and the drift that would make it a lie.

`sql/` is excluded from the Vercel bundle, so the DDL the application runs has
to live in `src/migrations.py` rather than being read from the .sql file. That
leaves two copies of the same schema, which is exactly the shape of bug this
project keeps finding in its own data sources: two files that agree today and
quietly stop agreeing later.

These tests hold them together by the only thing that matters — the set of
objects each one creates — rather than by byte equality, which would fail on a
reflowed comment and teach everyone to ignore it.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from src import migrations

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "sql" / "create_visitor_tracking.sql"

_OBJECT_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z_.]+)", re.I)


def _objects(sql: str) -> set[tuple[str, str]]:
    return {(kind.upper(), name.lower().replace("public.", ""))
            for kind, name in _OBJECT_RE.findall(sql)}


def test_embedded_ddl_and_sql_file_create_the_same_objects():
    """If these drift, the dashboard copy and the self-applying copy build
    different schemas — and whichever ran first wins silently."""
    assert _objects(migrations.VISITOR_TRACKING_DDL) == _objects(SQL_FILE.read_text())


def test_the_schema_actually_covers_what_tracking_writes():
    embedded = _objects(migrations.VISITOR_TRACKING_DDL)
    assert ("TABLE", "outreach_recipient") in embedded
    assert ("TABLE", "visitor_event") in embedded
    assert ("VIEW", "v_recipient_journey") in embedded


def test_every_statement_is_idempotent():
    """Two serverless cold starts can race. Nothing here may fail the second
    time, or one of them logs an error on every boot."""
    ddl = migrations.VISITOR_TRACKING_DDL
    for match in re.finditer(r"CREATE\s+(TABLE|INDEX)\s+(.{0,20})", ddl, re.I):
        assert match.group(2).upper().startswith("IF NOT EXISTS"), match.group(0)
    for match in re.finditer(r"CREATE\s+VIEW", ddl, re.I):
        pytest.fail("views must be CREATE OR REPLACE to be re-runnable")


def test_the_migration_refuses_to_be_a_migration_framework():
    """Additive only. A DROP or an ALTER ... DROP COLUMN here would run
    unattended against production on the next cold start."""
    ddl = migrations.VISITOR_TRACKING_DDL.upper()
    for forbidden in ("DROP TABLE", "DROP VIEW", "DROP COLUMN", "TRUNCATE",
                      "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in ddl, f"{forbidden} must never run unattended"


def test_the_finance_tables_are_never_touched():
    ddl = migrations.VISITOR_TRACKING_DDL.lower()
    for table in ("district_finances", "v_district_summary", "v_anomaly_flags"):
        assert table not in ddl


def test_ensure_schema_never_raises_without_a_pool():
    assert "skipped" in asyncio.run(migrations.ensure_schema(None))


def test_ensure_schema_swallows_a_broken_pool():
    """Startup must survive a database that is asleep, paused or refusing
    DDL — the site is designed to work with no database at all."""
    class Boom:
        def acquire(self):
            raise RuntimeError("connection refused")

    result = asyncio.run(migrations.ensure_schema(Boom()))
    assert result.startswith("ERROR")
    assert "connection refused" in result

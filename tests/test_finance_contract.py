"""Executed PostgreSQL contract tests for the finance summary reconciliation."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

DSN = os.getenv("FINANCE_CONTRACT_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="requires scripts/run_finance_contract_tests.py"
)
ROOT = Path(__file__).parents[1]
ANOMALY_SPEC = importlib.util.spec_from_file_location(
    "reconcile_anomaly_flags", ROOT / "scripts" / "reconcile_anomaly_flags.py"
)
anomaly = importlib.util.module_from_spec(ANOMALY_SPEC)
assert ANOMALY_SPEC.loader
ANOMALY_SPEC.loader.exec_module(anomaly)
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "finance_contract.json").read_text(
        encoding="utf-8"
    )
)

SUMMARY_COLUMNS = [
    "district_number",
    "district_name",
    "year",
    "total_revenue",
    "total_spend",
    "enrollment",
    "spend_per_student",
    "revenue_per_student",
    "instruction_spend",
    "debt_service",
    "capital_projects",
    "operating_spend",
    "library_media_spend",
    "curriculum_staff_dev_spend",
    "instructional_leadership_spend",
    "campus_admin_spend",
    "counseling_spend",
    "social_work_spend",
    "health_services_spend",
    "transportation_spend",
    "food_service_spend",
    "extracurricular_spend",
    "general_admin_spend",
    "plant_maintenance_spend",
    "security_spend",
    "data_processing_spend",
    "community_services_spend",
    "payroll_spend",
    "contracted_services_spend",
    "supplies_spend",
]
SUMMARY_TYPES = ["text", "text", *("bigint",) * 4, "numeric", "numeric", *("bigint",) * 22]
SUFFIX_PROJECTIONS = [
    ("all_funds_instruc_resource_media_service_exp_fct12", "library_media_spend"),
    ("all_funds_curriculum_staff_development_exp_fct13", "curriculum_staff_dev_spend"),
    ("all_funds_instruc_leadership_expend_fct21", "instructional_leadership_spend"),
    ("all_funds_campus_administration_expend_fct23", "campus_admin_spend"),
    ("all_funds_guidance_counseling_services_exp_fct31", "counseling_spend"),
    ("all_funds_social_work_services_exp_fct32", "social_work_spend"),
    ("all_funds_health_services_exp_fct33", "health_services_spend"),
    ("all_funds_transportation_expenditures_fct34", "transportation_spend"),
    ("all_funds_food_service_expenditures_fct35", "food_service_spend"),
    ("all_funds_extracurricular_expenditures_fct36", "extracurricular_spend"),
    ("all_funds_general_administrat_expend_fct41_92", "general_admin_spend"),
    ("all_funds_plant_maintenance_opera_expend_fct51", "plant_maintenance_spend"),
    ("all_funds_security_monitoring_service_expend_fct52", "security_spend"),
    ("all_funds_data_processing_services_expend_fct53", "data_processing_spend"),
    ("all_funds_community_services_fct61", "community_services_spend"),
    ("all_funds_total_payroll_expenditures", "payroll_spend"),
    (
        "all_funds_total_professional_contracted_services_expenditure",
        "contracted_services_spend",
    ),
    ("all_funds_total_supplies_materials_expenditures", "supplies_spend"),
]


def reconcile(connection) -> None:
    with connection.cursor() as cur:
        cur.execute(
            (ROOT / "sql" / "reconcile_finance_summary.sql").read_text(
                encoding="utf-8"
            )
        )


def recover(connection) -> None:
    with connection.cursor() as cur:
        cur.execute(
            (ROOT / "sql" / "recover_finance_summary.sql").read_text(
                encoding="utf-8"
            )
        )


def summary_select(
    *, corrected: bool, extended: bool, year_expression: str = "year", extra: bool = False
) -> str:
    spend = (
        "all_funds_total_disbursements::numeric / fall_survey_enrollment"
        if corrected
        else "(all_funds_total_disbursements / fall_survey_enrollment)::numeric"
    )
    revenue = (
        "all_funds_total_operating_revenue::numeric / fall_survey_enrollment"
        if corrected
        else "(all_funds_total_operating_revenue / fall_survey_enrollment)::numeric"
    )
    projections = [
        "district_number",
        "district_name",
        f"{year_expression} AS year",
        "all_funds_total_operating_revenue AS total_revenue",
        "all_funds_total_disbursements AS total_spend",
        "fall_survey_enrollment AS enrollment",
        f"CASE WHEN fall_survey_enrollment > 0 THEN round({spend}, 2) END AS spend_per_student",
        f"CASE WHEN fall_survey_enrollment > 0 THEN round({revenue}, 2) END AS revenue_per_student",
        "all_funds_instruction_transfer_expend_fct11_95 AS instruction_spend",
        "all_funds_debt_service_object_6500_for_td AS debt_service",
        "all_funds_capital_projects_object_6600_for_td AS capital_projects",
        "all_funds_total_operating_expenditures_by_obj AS operating_spend",
    ]
    if extended:
        projections.extend(f"{source} AS {target}" for source, target in SUFFIX_PROJECTIONS)
    if extra:
        projections.append("0::bigint AS unexpected_column")
    return "SELECT\n  " + ",\n  ".join(projections) + "\nFROM public.texas_school_finance"


ANOMALY_SELECT = """
WITH finance_changes AS (
  SELECT district_number, district_name, year, total_revenue, total_spend,
    enrollment, spend_per_student,
    lag(total_revenue) OVER w AS prev_revenue,
    lag(total_spend) OVER w AS prev_spend,
    lag(enrollment) OVER w AS prev_enrollment,
    lag(spend_per_student) OVER w AS prev_spend_per_student
  FROM public.v_finance_summary
  WINDOW w AS (PARTITION BY district_number ORDER BY year)
)
SELECT district_number, district_name, year,
  CASE WHEN prev_revenue > 0
    AND ((total_revenue - prev_revenue) / prev_revenue)::numeric < -0.15
    THEN true ELSE false END AS revenue_drop_flag,
  CASE WHEN prev_spend > 0
    AND ((total_spend - prev_spend) / prev_spend)::numeric > 0.20
    AND abs(coalesce(enrollment, 0) - coalesce(prev_enrollment, 0)) < 10
    THEN true ELSE false END AS spend_spike_flag,
  CASE WHEN prev_spend_per_student > 0 AND spend_per_student > 0
    AND ((spend_per_student - prev_spend_per_student) / prev_spend_per_student) > 0.15
    THEN true ELSE false END AS per_student_spike_flag,
  CASE WHEN prev_enrollment > 0 AND enrollment > 0
    AND ((enrollment - prev_enrollment)::double precision / prev_enrollment::double precision) < -0.10
    THEN true ELSE false END AS enrollment_decline_flag,
  total_revenue, prev_revenue, total_spend, prev_spend, enrollment,
  prev_enrollment, spend_per_student, prev_spend_per_student
FROM finance_changes
WHERE year > (SELECT min(year) FROM public.v_finance_summary)
"""


@pytest.fixture(scope="module")
def db():
    import psycopg2

    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    with connection.cursor() as cur:
        for role in ("anon", "authenticated", "nlp_reader", "finance_view_owner"):
            cur.execute(f"CREATE ROLE {role} NOLOGIN")
    yield connection
    connection.close()


def _base_catalog() -> list[tuple[str, str]]:
    return [tuple(item.rsplit(":", 1)) for item in FIXTURE["base_catalog"]]


def setup_state(
    db,
    starting_columns: int,
    *,
    view_year_expression: str = "year",
    base_year_type: str = "bigint",
    base_type_overrides: dict[str, str] | None = None,
    extra_view_column: bool = False,
) -> None:
    from psycopg2 import sql

    catalog = _base_catalog()
    assert len(catalog) == 140
    with db.cursor() as cur:
        cur.execute("ROLLBACK")
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION postgres")
        cur.execute("GRANT ALL ON SCHEMA public TO public")
        columns = [
            sql.SQL("{} {}").format(
                sql.Identifier(name),
                sql.SQL((base_type_overrides or {}).get(
                    name, base_year_type if name == "year" else data_type
                )),
            )
            for name, data_type in catalog
        ]
        cur.execute(
            sql.SQL("CREATE TABLE public.texas_school_finance ({})").format(
                sql.SQL(", ").join(columns)
            )
        )

        names = [name for name, _ in catalog]
        for row in [*FIXTURE["rows"], *FIXTURE["synthetic_rows"]]:
            values = []
            for name, data_type in catalog:
                if name in row:
                    values.append(row[name])
                elif data_type == "text":
                    values.append("")
                else:
                    values.append(0)
            cur.execute(
                sql.SQL("INSERT INTO public.texas_school_finance ({}) VALUES ({})").format(
                    sql.SQL(", ").join(map(sql.Identifier, names)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in names),
                ),
                values,
            )

        definition = summary_select(
            corrected=False,
            extended=starting_columns == 30,
            year_expression=view_year_expression,
            extra=extra_view_column,
        )
        cur.execute("CREATE VIEW public.v_finance_summary AS " + definition)
        cur.execute("ALTER VIEW public.v_finance_summary SET (security_barrier=true)")
        cur.execute(
            "GRANT SELECT ON public.texas_school_finance TO finance_view_owner"
        )
        cur.execute("ALTER VIEW public.v_finance_summary OWNER TO finance_view_owner")
        cur.execute("GRANT SELECT ON public.v_finance_summary TO anon, nlp_reader")
        cur.execute(
            "GRANT SELECT ON public.v_finance_summary TO authenticated WITH GRANT OPTION"
        )

        cur.execute("CREATE MATERIALIZED VIEW public.v_anomaly_flags AS " + ANOMALY_SELECT)
        cur.execute(
            "CREATE UNIQUE INDEX anomaly_district_year_idx "
            "ON public.v_anomaly_flags(district_number, year)"
        )
        cur.execute("CREATE INDEX anomaly_year_idx ON public.v_anomaly_flags(year)")
        cur.execute("ALTER MATERIALIZED VIEW public.v_anomaly_flags SET (fillfactor=90)")
        cur.execute("ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO finance_view_owner")
        cur.execute("GRANT SELECT ON public.v_anomaly_flags TO anon, nlp_reader")
        cur.execute(
            "GRANT SELECT ON public.v_anomaly_flags TO authenticated WITH GRANT OPTION"
        )
        # The other public read projections are intentionally minimal here: ACL
        # behavior, rather than their production projection text, is T3's unit.
        for name in ("v_spending_detail", "v_spending_breakdown", "v_district_similarity"):
            cur.execute(f"CREATE VIEW public.{name} AS SELECT district_number FROM public.v_finance_summary")
            cur.execute(f"ALTER VIEW public.{name} OWNER TO finance_view_owner")
            cur.execute(f"GRANT SELECT ON public.{name} TO PUBLIC")


def insert_source_rows(db, rows: list[dict[str, object]]) -> None:
    from psycopg2 import sql

    catalog = _base_catalog()
    names = [name for name, _ in catalog]
    with db.cursor() as cur:
        for row in rows:
            values = [
                row.get(name, "" if data_type == "text" else 0)
                for name, data_type in catalog
            ]
            cur.execute(
                sql.SQL("INSERT INTO public.texas_school_finance ({}) VALUES ({})").format(
                    sql.SQL(", ").join(map(sql.Identifier, names)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in names),
                ),
                values,
            )
        cur.execute("REFRESH MATERIALIZED VIEW public.v_anomaly_flags")


def anomaly_snapshot(db) -> dict:
    with db.cursor() as cur:
        return anomaly.capture(cur)


def anomaly_rows(cur):
    return _fetchall(
        cur,
        "SELECT * FROM public.v_anomaly_flags ORDER BY district_number,year",
    )


def _fetchall(cur, query: str):
    cur.execute(query)
    return cur.fetchall()


def full_snapshot(cur) -> dict[str, object]:
    relation_query = """
      SELECT c.oid, c.relname, pg_get_userbyid(c.relowner), c.reloptions,
        coalesce(c.relacl::text, ''), pg_get_viewdef(c.oid, true)
      FROM pg_class c
      WHERE c.oid IN ('public.v_finance_summary'::regclass,
                      'public.v_anomaly_flags'::regclass)
      ORDER BY c.relname
    """
    column_query = """
      SELECT c.relname, a.attnum, a.attname, format_type(a.atttypid, a.atttypmod)
      FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
      WHERE c.oid IN ('public.v_finance_summary'::regclass,
                      'public.v_anomaly_flags'::regclass)
        AND a.attnum > 0 AND NOT a.attisdropped
      ORDER BY c.relname, a.attnum
    """
    index_query = """
      SELECT ic.oid, ic.relname, pg_get_userbyid(ic.relowner), pg_get_indexdef(ic.oid)
      FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
      WHERE i.indrelid='public.v_anomaly_flags'::regclass
      ORDER BY ic.relname
    """
    return {
        "relations": _fetchall(cur, relation_query),
        "columns": _fetchall(cur, column_query),
        "indexes": _fetchall(cur, index_query),
        "summary_rows": _fetchall(
            cur,
            "SELECT * FROM public.v_finance_summary ORDER BY district_number, year",
        ),
        "anomaly_rows": _fetchall(
            cur,
            "SELECT * FROM public.v_anomaly_flags ORDER BY district_number, year",
        ),
    }


def object_metadata(snapshot: dict[str, object], relation_name: str):
    relation = next(row for row in snapshot["relations"] if row[1] == relation_name)
    indexes = snapshot["indexes"] if relation_name == "v_anomaly_flags" else None
    return relation[:5], indexes


def expected_per_student(row: dict[str, object]) -> tuple[Decimal | None, Decimal | None]:
    enrollment = row["fall_survey_enrollment"]
    if enrollment is None or enrollment <= 0:
        return None, None
    quantum = Decimal("0.01")
    spend = (Decimal(row["all_funds_total_disbursements"]) / Decimal(enrollment)).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    revenue = (
        Decimal(row["all_funds_total_operating_revenue"]) / Decimal(enrollment)
    ).quantize(quantum, rounding=ROUND_HALF_UP)
    return spend, revenue


def assert_correct_arithmetic(cur) -> None:
    fixture_rows = [*FIXTURE["rows"], *FIXTURE["synthetic_rows"]]
    actual = _fetchall(
        cur,
        "SELECT district_number, year, spend_per_student, revenue_per_student "
        "FROM public.v_finance_summary ORDER BY district_number, year",
    )
    expected = sorted(
        (
            row["district_number"],
            row["year"],
            *expected_per_student(row),
        )
        for row in fixture_rows
    )
    assert actual == expected
    dallas = next(row for row in actual if row[:2] == ("057905", 2025))
    assert dallas[2:] == (Decimal("23746.63"), Decimal("13529.52"))


@pytest.mark.parametrize("starting_columns", [12, 30])
def test_both_starting_contracts_reconcile_and_reapply_identically(db, starting_columns):
    setup_state(db, starting_columns)
    with db.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='texas_school_finance' "
            "ORDER BY ordinal_position"
        )
        assert cur.fetchall() == _base_catalog()
        before = full_snapshot(cur)

    reconcile(db)
    with db.cursor() as cur:
        after_first = full_snapshot(cur)
        assert object_metadata(after_first, "v_finance_summary") == object_metadata(
            before, "v_finance_summary"
        )
        assert object_metadata(after_first, "v_anomaly_flags") == object_metadata(
            before, "v_anomaly_flags"
        )
        assert [row[:3] for row in after_first["anomaly_rows"]] == [
            row[:3] for row in before["anomaly_rows"]
        ]
        assert [row[:6] + row[8:12] for row in after_first["summary_rows"]] == [
            row[:6] + row[8:12] for row in before["summary_rows"]
        ]
        summary_columns = [
            (row[2], row[3])
            for row in after_first["columns"]
            if row[0] == "v_finance_summary"
        ]
        assert summary_columns == list(zip(SUMMARY_COLUMNS, SUMMARY_TYPES, strict=True))
        assert_correct_arithmetic(cur)

    reconcile(db)
    with db.cursor() as cur:
        assert full_snapshot(cur) == after_first


@pytest.mark.parametrize("starting_columns", [12, 30])
def test_failure_after_replacement_and_refresh_rolls_back_each_start(db, starting_columns):
    setup_state(db, starting_columns)
    with db.cursor() as cur:
        before = full_snapshot(cur)
        broken = (ROOT / "sql" / "reconcile_finance_summary.sql").read_text(
            encoding="utf-8"
        )
        marker = "REFRESH MATERIALIZED VIEW public.v_anomaly_flags;"
        assert marker in broken
        broken = broken.replace(marker, marker + "\nSELECT 1/0;", 1)
        with pytest.raises(Exception, match="division by zero"):
            cur.execute(broken)
        cur.execute("ROLLBACK")
        assert full_snapshot(cur) == before


def test_post_commit_recovery_preserves_contract_then_repair_restores_math(db):
    setup_state(db, 12)
    reconcile(db)
    with db.cursor() as cur:
        corrected = full_snapshot(cur)
    recover(db)
    with db.cursor() as cur:
        recovered = full_snapshot(cur)
        assert object_metadata(recovered, "v_finance_summary") == object_metadata(
            corrected, "v_finance_summary"
        )
        assert object_metadata(recovered, "v_anomaly_flags") == object_metadata(
            corrected, "v_anomaly_flags"
        )
        assert len([row for row in recovered["columns"] if row[0] == "v_finance_summary"]) == 30
        cur.execute(
            "SELECT spend_per_student, revenue_per_student "
            "FROM public.v_finance_summary WHERE district_number='057905' AND year=2025"
        )
        assert cur.fetchone() == (Decimal("23746"), Decimal("13529"))
    reconcile(db)
    with db.cursor() as cur:
        repaired = full_snapshot(cur)
        assert object_metadata(repaired, "v_finance_summary") == object_metadata(
            corrected, "v_finance_summary"
        )
        assert object_metadata(repaired, "v_anomaly_flags") == object_metadata(
            corrected, "v_anomaly_flags"
        )
        assert_correct_arithmetic(cur)


@pytest.mark.parametrize(
    ("setup_kwargs", "starting_columns"),
    [
        ({"extra_view_column": True}, 30),
        ({"view_year_expression": "year::numeric"}, 12),
        ({"view_year_expression": "year::bigint", "base_year_type": "integer"}, 12),
    ],
    ids=["unexpected-view-shape", "unexpected-view-type", "unexpected-base-type"],
)
def test_unexpected_contracts_fail_before_mutation(db, setup_kwargs, starting_columns):
    setup_state(db, starting_columns, **setup_kwargs)
    with db.cursor() as cur:
        before = full_snapshot(cur)
        with pytest.raises(Exception, match="unexpected"):
            cur.execute(
                (ROOT / "sql" / "reconcile_finance_summary.sql").read_text(
                    encoding="utf-8"
                )
            )
        cur.execute("ROLLBACK")
        assert full_snapshot(cur) == before


def test_anomaly_transition_is_explicit_and_preserves_read_contract(db, tmp_path):
    setup_state(db, 12)
    reconcile(db)
    env = os.environ | {"FINANCE_CONTRACT_DSN": DSN}
    snapshot = tmp_path / "anomaly-preimage.json"
    inspect = subprocess.run(
        [
            sys.executable,
            "scripts/reconcile_anomaly_flags.py",
            "--dsn-env",
            "FINANCE_CONTRACT_DSN",
            "--inspect",
            "--snapshot",
            str(snapshot),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert inspect.returncode == 0, inspect.stderr
    result = subprocess.run(
        [
            sys.executable,
            "scripts/reconcile_anomaly_flags.py",
            "--dsn-env",
            "FINANCE_CONTRACT_DSN",
            "--apply",
            "--snapshot",
            str(snapshot),
            "--maintenance-window",
            "disposable-test",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    with db.cursor() as cur:
        cur.execute(
            "SELECT has_table_privilege('anon', 'public.v_anomaly_flags', 'SELECT'), "
            "pg_get_viewdef('public.v_anomaly_flags'::regclass, true)"
        )
        allowed, definition = cur.fetchone()
        assert allowed and "::numeric / prev_revenue" in definition
        assert "::numeric / prev_spend" in definition
        cur.execute((ROOT / "sql" / "harden_public_finance_read_contract.sql").read_text(encoding="utf-8"))
    verify_env = os.environ | {"FINANCE_VERIFY_DSN": DSN}
    verified = subprocess.run(
        [sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
        cwd=ROOT, env=verify_env, capture_output=True, text=True, encoding="utf-8",
    )
    assert verified.returncode == 0, verified.stderr
    assert "ANOMALY STATUS: corrected" in verified.stdout


def apply_anomaly_direct(guard: dict, *, failure_at=None, on_stage=None,
                         lock_timeout="1500ms", statement_timeout="15s"):
    import psycopg2

    conn = psycopg2.connect(DSN)
    try:
        result = anomaly.transition(
            conn, guard, guard, anomaly.corrected(guard["definition"]), "disposable-test",
            failure_at=failure_at, on_stage=on_stage,
            lock_timeout=lock_timeout, statement_timeout=statement_timeout,
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_anomaly_thresholds_null_safety_and_preserved_flags(db):
    setup_state(db, 12)
    reconcile(db)
    pairs = [
        ("REV84", 100, 100, 84, 100, 100, 100),
        ("REV85", 100, 100, 85, 100, 100, 100),
        ("SP121", 100, 100, 100, 121, 100, 109),
        ("SP120", 100, 100, 100, 120, 100, 109),
        ("DELTA10", 100, 100, 100, 121, 100, 110),
        ("PERSTU", 100, 100, 100, 120, 10, 10),
        ("ENROLL", 100, 100, 100, 100, 100, 89),
        ("ZEROPREV", 0, 0, 84, 121, 0, 0),
    ]
    rows = []
    for district, prev_rev, prev_spend, rev, spend, prev_enroll, enroll in pairs:
        rows.extend([
            {"district_number": district, "district_name": district, "year": 2200,
             "all_funds_total_operating_revenue": prev_rev,
             "all_funds_total_disbursements": prev_spend,
             "fall_survey_enrollment": prev_enroll},
            {"district_number": district, "district_name": district, "year": 2201,
             "all_funds_total_operating_revenue": rev,
             "all_funds_total_disbursements": spend,
             "fall_survey_enrollment": enroll},
        ])
    insert_source_rows(db, rows)
    guard = anomaly_snapshot(db)
    changed, _ = apply_anomaly_direct(guard)
    assert changed
    with db.cursor() as cur:
        cur.execute("""SELECT district_number,revenue_drop_flag,spend_spike_flag,
          per_student_spike_flag,enrollment_decline_flag FROM public.v_anomaly_flags
          WHERE year=2201 ORDER BY district_number""")
        actual = {row[0]: row[1:] for row in cur.fetchall()}
    expected = {
        "REV84": (Decimal(84 - 100) / Decimal(100) < Decimal("-0.15"), False, False, False),
        "REV85": (Decimal(85 - 100) / Decimal(100) < Decimal("-0.15"), False, False, False),
        "SP121": (False, Decimal(121 - 100) / Decimal(100) > Decimal("0.20"), False, False),
        "SP120": (False, Decimal(120 - 100) / Decimal(100) > Decimal("0.20"), False, False),
        "DELTA10": (False, False, False, False),
        "PERSTU": (False, False, Decimal(12 - 10) / Decimal(10) > Decimal("0.15"), False),
        "ENROLL": (False, False, False, Decimal(89 - 100) / Decimal(100) < Decimal("-0.10")),
        "ZEROPREV": (False, False, False, False),
    }
    assert actual == expected


def test_anomaly_reapply_fresh_corrected_snapshot_is_exact_noop(db):
    setup_state(db, 12)
    reconcile(db)
    apply_anomaly_direct(anomaly_snapshot(db))
    before = anomaly_snapshot(db)
    changed, returned = apply_anomaly_direct(before)
    assert not changed
    assert returned == before
    assert anomaly_snapshot(db) == before


@pytest.mark.parametrize(
    "failure_at", ["after_lock", "after_drop", "after_create", "after_restore", "after_assertions"]
)
def test_each_anomaly_failure_rolls_back_old_oid_rows_acl_and_indexes(db, failure_at):
    setup_state(db, 12)
    reconcile(db)
    guard = anomaly_snapshot(db)
    with db.cursor() as cur:
        before = full_snapshot(cur)
    with pytest.raises(RuntimeError, match="injected failure"):
        apply_anomaly_direct(guard, failure_at=failure_at)
    with db.cursor() as cur:
        assert full_snapshot(cur) == before
    assert anomaly_snapshot(db) == guard


def test_anomaly_receipt_recovery_uses_current_oids_then_allows_repair(db, tmp_path):
    setup_state(db, 12)
    reconcile(db)
    env = os.environ | {"FINANCE_CONTRACT_DSN": DSN}
    snapshot = tmp_path / "preimage.json"
    receipt = tmp_path / "committed-receipt.json"
    common = [sys.executable, "scripts/reconcile_anomaly_flags.py", "--dsn-env", "FINANCE_CONTRACT_DSN"]
    inspect = subprocess.run([*common, "--inspect", "--snapshot", str(snapshot)], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
    assert inspect.returncode == 0, inspect.stderr
    preimage = anomaly.load_wrapper(snapshot, "anomaly-preimage")
    applied = subprocess.run([*common, "--apply", "--snapshot", str(snapshot), "--receipt", str(receipt),
                              "--maintenance-window", "disposable-test"], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
    assert applied.returncode == 0, applied.stderr
    corrected_state = anomaly_snapshot(db)
    assert corrected_state["relation"]["oid"] != preimage["relation"]["oid"]
    tampered_value = anomaly.load_wrapper(receipt, "anomaly-transition-receipt")
    tampered_value["preimage"]["definition"] += "\nSELECT 1;"
    tampered_value["preimage_digest"] = anomaly.fingerprint(tampered_value["preimage"])
    tampered = tmp_path / "tampered-receipt.json"
    tampered.write_text(
        json.dumps(anomaly.make_wrapper("anomaly-transition-receipt", tampered_value)),
        encoding="utf-8",
    )
    rejected = subprocess.run([*common, "--recover", "--receipt", str(tampered),
                               "--maintenance-window", "disposable-test"], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8")
    assert rejected.returncode == 1
    assert "reviewed repair pair" in rejected.stderr
    assert anomaly_snapshot(db) == corrected_state
    recovered = subprocess.run([*common, "--recover", "--receipt", str(receipt),
                                "--maintenance-window", "disposable-test"], cwd=ROOT, env=env,
                               capture_output=True, text=True, encoding="utf-8")
    assert recovered.returncode == 0, recovered.stderr
    old_again = anomaly_snapshot(db)
    assert old_again["relation"]["oid"] not in {
        preimage["relation"]["oid"], corrected_state["relation"]["oid"]
    }
    assert "::numeric / prev_revenue" not in old_again["definition"]
    assert anomaly.metadata_contract(old_again) == anomaly.metadata_contract(preimage)
    apply_anomaly_direct(old_again)
    repaired = anomaly_snapshot(db)
    assert repaired["relation"]["oid"] != old_again["relation"]["oid"]
    assert "::numeric / prev_revenue" in repaired["definition"]


@pytest.mark.parametrize("dependency_kind", ["relation", "rowtype", "arraytype"])
def test_anomaly_dependency_is_rejected_before_drop(db, dependency_kind):
    setup_state(db, 12)
    reconcile(db)
    with db.cursor() as cur:
        if dependency_kind == "relation":
            cur.execute("CREATE VIEW public.anomaly_consumer AS SELECT district_number FROM public.v_anomaly_flags")
        elif dependency_kind == "rowtype":
            cur.execute("CREATE FUNCTION public.consume_anomaly(public.v_anomaly_flags) RETURNS int "
                        "LANGUAGE sql IMMUTABLE AS 'SELECT 1'")
        else:
            cur.execute("CREATE FUNCTION public.consume_anomaly_array(public.v_anomaly_flags[]) RETURNS int "
                        "LANGUAGE sql IMMUTABLE AS 'SELECT 1'")
        before = full_snapshot(cur)
    guard = anomaly_snapshot(db)
    with pytest.raises(RuntimeError, match="unsupported dependency"):
        apply_anomaly_direct(guard)
    with db.cursor() as cur:
        assert full_snapshot(cur) == before


def test_anomaly_rejects_column_acl_and_security_label_contract_before_drop(db):
    setup_state(db, 12)
    reconcile(db)
    with db.cursor() as cur:
        cur.execute("REVOKE SELECT ON public.v_anomaly_flags FROM anon")
        cur.execute("GRANT SELECT(district_number) ON public.v_anomaly_flags TO anon")
        before = full_snapshot(cur)
    guard = anomaly_snapshot(db)
    with pytest.raises(RuntimeError, match="column ACL"):
        apply_anomaly_direct(guard)
    with db.cursor() as cur:
        assert full_snapshot(cur) == before
    synthetic = json.loads(json.dumps(guard))
    synthetic["columns"][0][5] = "{anon=r/finance_view_owner}"
    with pytest.raises(RuntimeError, match="column ACL"):
        anomaly.validate_supported(synthetic)
    synthetic = json.loads(json.dumps(guard))
    synthetic["security_labels"] = [["pg_class", guard["relation"]["oid"], 0, "provider", "label"]]
    with pytest.raises(RuntimeError, match="security labels"):
        anomaly.validate_supported(synthetic)


def test_anomaly_metadata_comments_defaults_and_grant_options_survive(db):
    setup_state(db, 12)
    reconcile(db)
    with db.cursor() as cur:
        cur.execute("COMMENT ON MATERIALIZED VIEW public.v_anomaly_flags IS 'reviewed relation'")
        cur.execute("COMMENT ON COLUMN public.v_anomaly_flags.district_number IS 'reviewed column'")
        cur.execute("COMMENT ON INDEX public.anomaly_year_idx IS 'reviewed index'")
        cur.execute("COMMENT ON TYPE public.v_anomaly_flags IS 'reviewed row type'")
        cur.execute("GRANT SELECT ON public.v_anomaly_flags TO nlp_reader WITH GRANT OPTION")
        cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE finance_view_owner IN SCHEMA public "
                    "GRANT SELECT ON TABLES TO PUBLIC")
    before = anomaly_snapshot(db)
    apply_anomaly_direct(before)
    after = anomaly_snapshot(db)
    assert anomaly.metadata_contract(after) == anomaly.metadata_contract(before)
    assert before["default_privileges"] == after["default_privileges"]


def test_anomaly_reader_contention_and_tool_serialization_roll_back(db):
    import psycopg2

    setup_state(db, 12)
    reconcile(db)
    guard = anomaly_snapshot(db)
    with db.cursor() as cur:
        before = full_snapshot(cur)

    reader = psycopg2.connect(DSN)
    try:
        reader.cursor().execute("SELECT count(*) FROM public.v_anomaly_flags")
        with pytest.raises(Exception) as reader_error:
            apply_anomaly_direct(guard, lock_timeout="250ms", statement_timeout="2s")
        assert "lock timeout" in str(reader_error.value).lower()
    finally:
        reader.rollback()
        reader.close()

    holder = psycopg2.connect(DSN)
    try:
        holder.cursor().execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (anomaly.LOCK_KEY,))
        with pytest.raises(Exception) as tool_error:
            apply_anomaly_direct(guard, lock_timeout="250ms", statement_timeout="500ms")
        assert "lock timeout" in str(tool_error.value).lower()
    finally:
        holder.rollback()
        holder.close()
    with db.cursor() as cur:
        assert full_snapshot(cur) == before


def test_reads_and_late_dependency_wait_behind_exclusive_transition_lock(db):
    import psycopg2

    setup_state(db, 12)
    reconcile(db)
    guard = anomaly_snapshot(db)
    locked = threading.Event()
    release = threading.Event()
    outcome: list[object] = []

    def barrier(stage):
        if stage == "after_lock":
            locked.set()
            assert release.wait(5)

    def worker():
        try:
            outcome.append(apply_anomaly_direct(guard, on_stage=barrier, statement_timeout="10s"))
        except Exception as exc:  # surfaced by the assertion below
            outcome.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert locked.wait(5)
    for statement in (
        "SELECT count(*) FROM public.v_anomaly_flags",
        "CREATE VIEW public.late_anomaly_consumer AS SELECT district_number FROM public.v_anomaly_flags",
    ):
        contender = psycopg2.connect(DSN)
        try:
            with contender.cursor() as cur:
                cur.execute("SET lock_timeout='250ms'")
                with pytest.raises(Exception, match="lock timeout"):
                    cur.execute(statement)
            contender.rollback()
        finally:
            contender.close()
    release.set()
    thread.join(10)
    assert not thread.is_alive()
    assert outcome and not isinstance(outcome[0], Exception), outcome
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.v_anomaly_flags")
        assert cur.fetchone()[0] >= 0
        cur.execute("SELECT to_regclass('public.late_anomaly_consumer')")
        assert cur.fetchone()[0] is None


def test_owner_drift_committed_while_waiting_is_detected_after_lock(db):
    import psycopg2

    setup_state(db, 12)
    reconcile(db)
    guard = anomaly_snapshot(db)
    reader = psycopg2.connect(DSN)
    reader.cursor().execute("SELECT count(*) FROM public.v_anomaly_flags")
    drift_conn = psycopg2.connect(DSN)
    transition_conn = psycopg2.connect(DSN)
    drift_pid = drift_conn.get_backend_pid()
    transition_pid = transition_conn.get_backend_pid()
    results: list[tuple[str, object]] = []
    inspected = threading.Event()
    allow_owner_lock = threading.Event()

    def drift_worker():
        try:
            drift_conn.cursor().execute("ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO postgres")
            drift_conn.commit()
            results.append(("drift", "committed"))
        except Exception as exc:
            drift_conn.rollback()
            results.append(("drift", exc))

    def transition_worker():
        try:
            def barrier(stage):
                if stage == "before_owner_lock":
                    inspected.set()
                    assert allow_owner_lock.wait(5)
            anomaly.transition(transition_conn, guard, guard, anomaly.corrected(guard["definition"]),
                               "disposable-test", statement_timeout="8s", on_stage=barrier)
            transition_conn.commit()
            results.append(("transition", "committed"))
        except Exception as exc:
            transition_conn.rollback()
            results.append(("transition", exc))

    def wait_for_lock(pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with db.cursor() as cur:
                cur.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,))
                row = cur.fetchone()
            if row and row[0] == "Lock":
                return
            time.sleep(0.02)
        raise AssertionError(f"backend {pid} did not enter a lock wait")

    transition_thread = threading.Thread(target=transition_worker)
    transition_thread.start()
    assert inspected.wait(5)
    drift_thread = threading.Thread(target=drift_worker)
    drift_thread.start()
    wait_for_lock(drift_pid)
    allow_owner_lock.set()
    wait_for_lock(transition_pid)
    reader.rollback()
    reader.close()
    drift_thread.join(5)
    transition_thread.join(5)
    drift_conn.close()
    transition_conn.close()
    assert ("drift", "committed") in results
    transition_result = next(value for name, value in results if name == "transition")
    assert isinstance(transition_result, RuntimeError)
    assert "catalog drift while acquiring relation lock" in str(transition_result)
    with db.cursor() as cur:
        cur.execute("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.v_anomaly_flags'::regclass")
        assert cur.fetchone()[0] == "postgres"


def test_public_read_contract_and_readonly_verifier(db):
    setup_state(db, 12)
    reconcile(db)
    contract = (ROOT / "sql" / "harden_public_finance_read_contract.sql").read_text(encoding="utf-8")
    with db.cursor() as cur:
        # Start from the permissive legacy state that the reviewed PR repaired.
        cur.execute("GRANT ALL ON public.texas_school_finance TO PUBLIC,anon,authenticated,nlp_reader")
        cur.execute("GRANT ALL ON public.v_finance_summary,public.v_spending_detail,"
                    "public.v_spending_breakdown,public.v_district_similarity,"
                    "public.v_anomaly_flags TO PUBLIC,anon,authenticated,nlp_reader")
        cur.execute(contract)
        cur.execute(contract)  # The ACL repair is safely re-applicable.
        objects = [name for name, _ in (
            ("v_finance_summary", "v"), ("v_spending_detail", "v"),
            ("v_spending_breakdown", "v"), ("v_district_similarity", "v"),
            ("v_anomaly_flags", "m"),
        )]
        expected_counts = {}
        for name in objects:
            cur.execute(f"SELECT count(*) FROM public.{name}")
            expected_counts[name] = cur.fetchone()[0]
        for role in ("anon", "authenticated"):
            for name in objects:
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                    cur.execute("SELECT has_table_privilege(%s,%s,%s)",
                                (role, f"public.{name}", privilege))
                    assert cur.fetchone()[0] is (privilege == "SELECT")
                cur.execute(f"SET ROLE {role}")
                cur.execute(f"SELECT count(*) FROM public.{name}")
                assert cur.fetchone()[0] == expected_counts[name]
                cur.execute("RESET ROLE")
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                cur.execute("SELECT has_table_privilege(%s,'public.texas_school_finance',%s)", (role, privilege))
                assert not cur.fetchone()[0]
            cur.execute("SELECT has_schema_privilege(%s,'public','CREATE')", (role,))
            assert not cur.fetchone()[0]
            cur.execute(f"SET ROLE {role}")
            with pytest.raises(Exception, match="permission denied"):
                cur.execute(f"CREATE TABLE public.forbidden_{role}(id int)")
            cur.execute("RESET ROLE")
        for name in objects:
            cur.execute("SELECT has_table_privilege('nlp_reader',%s,'SELECT')", (f"public.{name}",))
            assert cur.fetchone()[0] is (name in {"v_finance_summary", "v_anomaly_flags"})
        cur.execute("SELECT has_schema_privilege('nlp_reader','public','CREATE')")
        assert not cur.fetchone()[0]
        cur.execute(
            "SELECT has_table_privilege('nlp_reader','public.texas_school_finance',"
            "'SELECT,INSERT,UPDATE,DELETE')"
        )
        assert not cur.fetchone()[0]
    env = os.environ | {"FINANCE_VERIFY_DSN": DSN}
    result = subprocess.run([sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "ENROLLMENT EXCEPTIONS: nonpositive_or_null=6; populated_values=0" in result.stdout
    assert "ANOMALY STATUS: DEFERRED" in result.stdout


def test_readonly_verifier_reports_broken_grants_without_mutating(db):
    setup_state(db, 12)
    reconcile(db)
    with db.cursor() as cur:
        cur.execute((ROOT / "sql" / "harden_public_finance_read_contract.sql").read_text(encoding="utf-8"))
        cur.execute("GRANT SELECT ON public.texas_school_finance TO anon")
    env = os.environ | {"FINANCE_VERIFY_DSN": DSN}
    result = subprocess.run([sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 1
    assert "anon has SELECT on base table" in result.stderr


def test_readonly_verifier_detects_latest_year_arithmetic(db):
    setup_state(db, 30)
    with db.cursor() as cur:
        cur.execute((ROOT / "sql" / "harden_public_finance_read_contract.sql").read_text(encoding="utf-8"))
    env = os.environ | {"FINANCE_VERIFY_DSN": DSN}
    result = subprocess.run(
        [sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
        cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True,
    )
    assert result.returncode == 1
    assert "latest eligible arithmetic mismatches" in result.stderr
    assert "ENROLLMENT EXCEPTIONS:" in result.stdout


def test_readonly_verifier_detects_exact_suffix_types_math_and_redacts_connection_details(db):
    setup_state(
        db,
        30,
        base_type_overrides={"all_funds_total_supplies_materials_expenditures": "numeric"},
    )
    with db.cursor() as cur:
        cur.execute((ROOT / "sql" / "harden_public_finance_read_contract.sql").read_text(encoding="utf-8"))
    env = os.environ | {"FINANCE_VERIFY_DSN": DSN}
    result = subprocess.run([sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 1
    assert "summary columns/types unexpected" in result.stderr

    secret = "TOP-SECRET-PASSWORD-4931"
    bad_dsn = f"postgresql://secret-user:{secret}@127.0.0.1:1/secret-database?application_name=secret-app"
    env["FINANCE_VERIFY_DSN"] = bad_dsn
    result = subprocess.run([sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True)
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    for fragment in (bad_dsn, secret, "secret-user", "secret-database", "secret-app"):
        assert fragment not in combined

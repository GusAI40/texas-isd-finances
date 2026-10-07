"""Executed PostgreSQL contract tests for the finance summary reconciliation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

DSN = os.getenv("FINANCE_CONTRACT_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="requires scripts/run_finance_contract_tests.py"
)
ROOT = Path(__file__).parents[1]
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
                sql.SQL(base_year_type if name == "year" else data_type),
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


def test_public_read_contract_and_readonly_verifier(db, tmp_path):
    setup_state(db, 12)
    reconcile(db)
    contract = (ROOT / "sql" / "harden_public_finance_read_contract.sql").read_text(encoding="utf-8")
    with db.cursor() as cur:
        cur.execute(contract)
        cur.execute(contract)  # The ACL repair is safely re-applicable.
        for role in ("anon", "authenticated"):
            cur.execute("SELECT has_table_privilege(%s, 'public.v_spending_detail', 'SELECT')", (role,))
            assert cur.fetchone()[0]
            cur.execute("SELECT has_table_privilege(%s, 'public.texas_school_finance', 'SELECT')", (role,))
            assert not cur.fetchone()[0]
        cur.execute("SELECT has_table_privilege('nlp_reader', 'public.v_spending_detail', 'SELECT')")
        assert not cur.fetchone()[0]
    env = os.environ | {"FINANCE_VERIFY_DSN": DSN}
    result = subprocess.run([sys.executable, "scripts/verify_finance_contract.py", "--dsn-env", "FINANCE_VERIFY_DSN"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stderr


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
    assert "base-table or mutation privilege" in result.stderr

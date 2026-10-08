"""Read-only finance catalog, access, dependency, and arithmetic verifier."""
from __future__ import annotations

import argparse
import os
import sys

PUBLIC_OBJECTS = (
    ("v_finance_summary", "v"), ("v_spending_detail", "v"),
    ("v_spending_breakdown", "v"), ("v_district_similarity", "v"),
    ("v_anomaly_flags", "m"),
)
SUMMARY_COLUMNS = [
    ("district_number", "text"), ("district_name", "text"), ("year", "bigint"),
    ("total_revenue", "bigint"), ("total_spend", "bigint"), ("enrollment", "bigint"),
    ("spend_per_student", "numeric"), ("revenue_per_student", "numeric"),
    ("instruction_spend", "bigint"), ("debt_service", "bigint"),
    ("capital_projects", "bigint"), ("operating_spend", "bigint"),
    ("library_media_spend", "bigint"), ("curriculum_staff_dev_spend", "bigint"),
    ("instructional_leadership_spend", "bigint"), ("campus_admin_spend", "bigint"),
    ("counseling_spend", "bigint"), ("social_work_spend", "bigint"),
    ("health_services_spend", "bigint"), ("transportation_spend", "bigint"),
    ("food_service_spend", "bigint"), ("extracurricular_spend", "bigint"),
    ("general_admin_spend", "bigint"), ("plant_maintenance_spend", "bigint"),
    ("security_spend", "bigint"), ("data_processing_spend", "bigint"),
    ("community_services_spend", "bigint"), ("payroll_spend", "bigint"),
    ("contracted_services_spend", "bigint"), ("supplies_spend", "bigint"),
]
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def inspect(cur) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    evidence: list[str] = []
    cur.execute("SHOW transaction_read_only")
    if cur.fetchone()[0] != "on":
        problems.append("verification transaction is not read-only")

    cur.execute("""SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname='public' AND c.relname = ANY(%s) ORDER BY c.relname""",
                ([name for name, _ in PUBLIC_OBJECTS],))
    found = dict(cur.fetchall())
    for name, kind in PUBLIC_OBJECTS:
        if found.get(name) != kind:
            problems.append(f"object {name}: expected {kind}, found {found.get(name, 'absent')}")

    cur.execute("""SELECT column_name,data_type FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='v_finance_summary'
                   ORDER BY ordinal_position""")
    columns = cur.fetchall()
    if columns != SUMMARY_COLUMNS:
        problems.append(f"summary columns/types unexpected: {columns}")

    cur.execute("""SELECT count(*), count(*) FILTER (WHERE spend_per_student IS NOT NULL
                         OR revenue_per_student IS NOT NULL)
                   FROM public.v_finance_summary WHERE enrollment IS NULL OR enrollment <= 0""")
    enrollment_exceptions, populated_exceptions = cur.fetchone()
    evidence.append(
        f"ENROLLMENT EXCEPTIONS: nonpositive_or_null={enrollment_exceptions}; "
        f"populated_values={populated_exceptions}"
    )
    if populated_exceptions:
        problems.append(f"enrollment exceptions with per-student values: {populated_exceptions}")

    cur.execute("""WITH latest AS (
                     SELECT district_number,max(year) AS year FROM public.v_finance_summary
                     WHERE enrollment > 0 GROUP BY district_number
                   )
                   SELECT count(*), count(*) FILTER (WHERE
                     s.spend_per_student IS DISTINCT FROM round(s.total_spend::numeric/s.enrollment,2)
                     OR s.revenue_per_student IS DISTINCT FROM round(s.total_revenue::numeric/s.enrollment,2))
                   FROM public.v_finance_summary s JOIN latest USING (district_number,year)""")
    eligible, mismatches = cur.fetchone()
    evidence.append(f"LATEST-YEAR ARITHMETIC: eligible={eligible}; mismatches={mismatches}")
    if mismatches:
        problems.append(f"latest eligible arithmetic mismatches: {mismatches}")

    for role in ("anon", "authenticated"):
        for name, _ in PUBLIC_OBJECTS:
            for privilege in PRIVILEGES:
                cur.execute("SELECT has_table_privilege(%s, %s, %s)",
                            (role, f"public.{name}", privilege))
                allowed = cur.fetchone()[0]
                if allowed != (privilege == "SELECT"):
                    problems.append(f"{role} {privilege} on {name} is {allowed}, expected {privilege == 'SELECT'}")
        for privilege in PRIVILEGES:
            cur.execute("SELECT has_table_privilege(%s, 'public.texas_school_finance', %s)",
                        (role, privilege))
            if cur.fetchone()[0]:
                problems.append(f"{role} has {privilege} on base table")
        cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (role,))
        if cur.fetchone()[0]:
            problems.append(f"{role} has CREATE on public schema")

    for name, _ in PUBLIC_OBJECTS:
        for privilege in PRIVILEGES:
            cur.execute("SELECT has_table_privilege('nlp_reader', %s, %s)",
                        (f"public.{name}", privilege))
            allowed = cur.fetchone()[0]
            expected = privilege == "SELECT" and name in {"v_finance_summary", "v_anomaly_flags"}
            if allowed != expected:
                problems.append(f"nlp_reader {privilege} on {name} is {allowed}, expected {expected}")
    for privilege in PRIVILEGES:
        cur.execute("SELECT has_table_privilege('nlp_reader', 'public.texas_school_finance', %s)",
                    (privilege,))
        if cur.fetchone()[0]:
            problems.append(f"nlp_reader has {privilege} on base table")
    cur.execute("SELECT has_schema_privilege('nlp_reader', 'public', 'CREATE')")
    if cur.fetchone()[0]:
        problems.append("nlp_reader has CREATE on public schema")

    cur.execute("""SELECT EXISTS (
      SELECT 1 FROM pg_rewrite r JOIN pg_depend d ON d.classid='pg_rewrite'::regclass
        AND d.objid=r.oid AND d.refclassid='pg_class'::regclass
      WHERE r.ev_class='public.v_anomaly_flags'::regclass
        AND d.refobjid='public.v_finance_summary'::regclass)""")
    if not cur.fetchone()[0]:
        problems.append("anomaly materialized view dependency on finance summary is absent")

    cur.execute("SELECT pg_get_viewdef('public.v_anomaly_flags'::regclass,true)")
    definition = cur.fetchone()[0]
    revenue_fixed = "(total_revenue - prev_revenue)::numeric / prev_revenue" in definition
    spend_fixed = "(total_spend - prev_spend)::numeric / prev_spend" in definition
    if revenue_fixed and spend_fixed:
        evidence.append("ANOMALY STATUS: corrected revenue/spend numeric ratios verified")
    elif not revenue_fixed and not spend_fixed:
        evidence.append("ANOMALY STATUS: DEFERRED defective integer revenue/spend ratios remain")
    else:
        problems.append("anomaly ratio correction is partial")
    return problems, evidence


def failures(cur) -> list[str]:
    """Compatibility helper for focused callers that only need failures."""
    return inspect(cur)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn-env", required=True)
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"environment variable {args.dsn_env} is required")
    try:
        import psycopg2
        with psycopg2.connect(dsn) as conn:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '30s'; SET LOCAL lock_timeout = '5s'")
                problems, evidence = inspect(cur)
            conn.rollback()
    except Exception as exc:
        # Connection exceptions can echo hosts, user names, query strings, and
        # passwords independently. Report only the exception class.
        print(f"FAIL finance verification: {type(exc).__name__}: connection or verification error",
              file=sys.stderr)
        return 1
    for line in evidence:
        print(line)
    if problems:
        print("FAIL finance verification:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("PASS finance read contract: exact columns/types, dependencies, effective grants, and arithmetic verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

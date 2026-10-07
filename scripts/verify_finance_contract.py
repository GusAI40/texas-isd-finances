"""Read-only finance catalog, access, and arithmetic verifier.

The connection string is obtained only from the named environment variable. It
is deliberately never echoed, including on connection errors.
"""
from __future__ import annotations

import argparse
import os
import sys

PUBLIC_OBJECTS = (
    ("v_finance_summary", "v"), ("v_spending_detail", "v"),
    ("v_spending_breakdown", "v"), ("v_district_similarity", "v"),
    ("v_anomaly_flags", "m"),
)
SUMMARY_PREFIX = [
    ("district_number", "text"), ("district_name", "text"), ("year", "bigint"),
    ("total_revenue", "bigint"), ("total_spend", "bigint"), ("enrollment", "bigint"),
    ("spend_per_student", "numeric"), ("revenue_per_student", "numeric"),
    ("instruction_spend", "bigint"), ("debt_service", "bigint"),
    ("capital_projects", "bigint"), ("operating_spend", "bigint"),
]


def failures(cur) -> list[str]:
    problems: list[str] = []
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
    if columns[:len(SUMMARY_PREFIX)] != SUMMARY_PREFIX or len(columns) not in (12, 30):
        problems.append(f"summary columns/types unexpected: {columns}")
    cur.execute("""SELECT count(*) FROM public.v_finance_summary
                   WHERE (enrollment IS NULL OR enrollment <= 0)
                     AND (spend_per_student IS NOT NULL OR revenue_per_student IS NOT NULL)""")
    if cur.fetchone()[0]:
        problems.append("nonpositive or null enrollment has a per-student value")
    cur.execute("""SELECT count(*) FROM public.v_finance_summary
                   WHERE enrollment > 0 AND year=(SELECT max(year) FROM public.v_finance_summary)
                     AND (spend_per_student <> round(total_spend::numeric/enrollment,2)
                       OR revenue_per_student <> round(total_revenue::numeric/enrollment,2))""")
    if cur.fetchone()[0]:
        problems.append("latest eligible rows have per-student arithmetic mismatches")
    for role in ("anon", "authenticated"):
        for name, _ in PUBLIC_OBJECTS:
            cur.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", (role, f"public.{name}"))
            if not cur.fetchone()[0]:
                problems.append(f"{role} lacks SELECT on {name}")
        cur.execute("SELECT has_table_privilege(%s, 'public.texas_school_finance', 'SELECT,INSERT,UPDATE,DELETE')", (role,))
        if cur.fetchone()[0]:
            problems.append(f"{role} has base-table or mutation privilege")
    for name, _ in PUBLIC_OBJECTS:
        cur.execute("SELECT has_table_privilege('nlp_reader', %s, 'SELECT')", (f"public.{name}",))
        allowed = cur.fetchone()[0]
        expected = name in {"v_finance_summary", "v_anomaly_flags"}
        if allowed != expected:
            problems.append(f"nlp_reader access to {name} is {allowed}, expected {expected}")
    cur.execute("SELECT has_table_privilege('nlp_reader', 'public.texas_school_finance', 'SELECT')")
    if cur.fetchone()[0]:
        problems.append("nlp_reader can read the base table")
    return problems


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
            with conn.cursor() as cur:
                cur.execute("BEGIN READ ONLY")
                cur.execute("SET LOCAL statement_timeout = '30s'; SET LOCAL lock_timeout = '5s'")
                problems = failures(cur)
                cur.execute("ROLLBACK")
    except Exception as exc:
        message = str(exc).replace(dsn, "[redacted-dsn]")
        print(f"FAIL finance verification: {type(exc).__name__}: {message}", file=sys.stderr)
        return 1
    if problems:
        print("FAIL finance verification:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("PASS finance read contract: columns/types, public/NLP effective grants, and arithmetic verified")
    print("DEFERRED: anomaly revenue/spend ratio formulas require the separate guarded transition.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

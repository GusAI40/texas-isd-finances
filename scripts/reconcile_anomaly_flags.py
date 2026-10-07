"""Guarded replacement of public.v_anomaly_flags.

Inspection is read-only.  Apply needs its digest-bound inspection, an explicit
maintenance-window acknowledgement, an advisory transaction lock, and a fresh
post-owner-lock inspection.  PostgreSQL does not support LOCK TABLE on a
materialized view; ALTER MATERIALIZED VIEW OWNER TO same-owner is the supported
PG17 path that obtains AccessExclusiveLock before replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

NAME = "public.v_anomaly_flags"
LOCK_KEY = "texas-isd-finances:v_anomaly_flags:v1"


def packed(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(packed(snapshot)).hexdigest()


def capture(cur) -> dict:
    """Only JSON values: an inspection is evidence, never executable SQL."""
    cur.execute("""SELECT current_database(), (SELECT oid FROM pg_database WHERE datname=current_database()),
      current_setting('server_version_num'), inet_server_addr()::text, inet_server_port()""")
    target = list(cur.fetchone())
    cur.execute("""SELECT c.oid,c.reltype,t.typarray,c.xmin::text,pg_get_userbyid(c.relowner),
      c.relpersistence,c.reloptions,c.reltablespace,am.amname,c.relispopulated,
      obj_description(c.oid,'pg_class'),pg_get_viewdef(c.oid,true)
      FROM pg_class c JOIN pg_type t ON t.oid=c.reltype LEFT JOIN pg_am am ON am.oid=c.relam
      WHERE c.oid=%s::regclass""", (NAME,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"required {NAME} is absent")
    relation = {"oid": row[0], "rowtype_oid": row[1], "arraytype_oid": row[2], "xmin": row[3],
                "owner": row[4], "persistence": row[5], "options": row[6], "tablespace_oid": row[7],
                "access_method": row[8], "populated": row[9], "comment": row[10]}
    definition = row[11]
    cur.execute("""SELECT attnum,attname,format_type(atttypid,atttypmod),attnotnull,
      col_description(attrelid,attnum),attacl::text FROM pg_attribute WHERE attrelid=%s::regclass
      AND attnum>0 AND NOT attisdropped ORDER BY attnum""", (NAME,))
    columns = [list(r) for r in cur]
    cur.execute("""SELECT i.indexrelid,pg_get_indexdef(i.indexrelid),obj_description(i.indexrelid,'pg_class')
      FROM pg_index i WHERE i.indrelid=%s::regclass ORDER BY i.indexrelid""", (NAME,))
    indexes = [list(r) for r in cur]
    # Cover the relation, row type and array type. Dependencies are deliberately
    # snapshotted rather than filtered by broad deptype categories.
    cur.execute("""SELECT classid::regclass::text,objid::text,objsubid,refclassid::regclass::text,
      refobjid::text,refobjsubid,deptype FROM pg_depend WHERE refobjid IN
      (%s::regclass,(SELECT reltype FROM pg_class WHERE oid=%s::regclass),
       (SELECT typarray FROM pg_type WHERE oid=(SELECT reltype FROM pg_class WHERE oid=%s::regclass)))
      ORDER BY 1,2,3,4,5,6,7""", (NAME, NAME, NAME))
    dependencies = [list(r) for r in cur]
    cur.execute("""SELECT coalesce(pg_get_userbyid(x.grantee),'PUBLIC'),x.privilege_type,
      CASE WHEN x.is_grantable THEN 'YES' ELSE 'NO' END
      FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
      WHERE c.oid=%s::regclass ORDER BY 1,2,3""", (NAME,))
    grants = [list(r) for r in cur]
    cur.execute("SELECT evtname FROM pg_event_trigger WHERE evtenabled <> 'D' ORDER BY evtname")
    triggers = [r[0] for r in cur]
    return {"version": 1, "target": target, "relation": relation, "definition": definition,
            "columns": columns, "indexes": indexes, "dependencies": dependencies,
            "grants": grants, "event_triggers": triggers}


def load(path: Path) -> dict:
    wrapper = json.loads(path.read_text(encoding="utf-8"))
    snapshot = wrapper.get("snapshot")
    if not isinstance(snapshot, dict) or wrapper.get("digest") != fingerprint(snapshot):
        raise RuntimeError("invalid or modified inspection snapshot")
    return snapshot


def corrected(definition: str) -> str:
    result = definition.replace("(total_revenue - prev_revenue) / prev_revenue",
                                "(total_revenue - prev_revenue)::numeric / prev_revenue")
    result = result.replace("(total_spend - prev_spend) / prev_spend",
                            "(total_spend - prev_spend)::numeric / prev_spend")
    already_correct = "::numeric / prev_revenue" in definition and "::numeric / prev_spend" in definition
    if result == definition and not already_correct:
        raise RuntimeError("reviewed anomaly expressions were not found")
    return result


def restore_grants(cur, grants: list[list[str]]) -> None:
    for role in ("PUBLIC", "anon", "authenticated", "nlp_reader"):
        cur.execute(sql.SQL("REVOKE ALL PRIVILEGES ON TABLE public.v_anomaly_flags FROM {}")
                    .format(sql.SQL(role)))
    for grantee, privilege, grantable in grants:
        role = sql.SQL("PUBLIC") if grantee == "PUBLIC" else sql.Identifier(grantee)
        cur.execute(sql.SQL("GRANT {} ON TABLE public.v_anomaly_flags TO {}{}").format(
            sql.SQL(privilege), role, sql.SQL(" WITH GRANT OPTION") if grantable == "YES" else sql.SQL("")))


def restore_supported_metadata(cur, expected: dict) -> None:
    """Restore only the reviewed metadata set; reject anything we cannot prove."""
    relation = expected["relation"]
    if relation["tablespace_oid"] or relation["access_method"] not in ("heap",):
        raise RuntimeError("nondefault tablespace or access method requires a reviewed transition")
    options = relation["options"] or []
    for option in options:
        match = __import__("re").fullmatch(r"fillfactor=(\d{1,3})", option)
        if not match or not 10 <= int(match.group(1)) <= 100:
            raise RuntimeError(f"unsupported materialized-view reloption: {option!r}")
        cur.execute(sql.SQL("ALTER MATERIALIZED VIEW public.v_anomaly_flags SET (fillfactor={})")
                    .format(sql.Literal(int(match.group(1)))))
    if relation["comment"] is not None:
        cur.execute("COMMENT ON MATERIALIZED VIEW public.v_anomaly_flags IS %s", (relation["comment"],))
    for _, name, _, _, comment, acl in expected["columns"]:
        if acl:
            raise RuntimeError("column ACLs require a reviewed transition")
        if comment is not None:
            cur.execute(sql.SQL("COMMENT ON COLUMN public.v_anomaly_flags.{} IS %s")
                        .format(sql.Identifier(name)), (comment,))
    for _, _, comment in expected["indexes"]:
        if comment is not None:
            # Index names are encoded in pg_get_indexdef; comments on indexes
            # need an explicit supported migration rather than SQL reconstruction.
            raise RuntimeError("index comments require a reviewed transition")


def transition(conn, expected: dict, ack: str, recover: bool) -> bool:
    if not ack:
        raise RuntimeError("--maintenance-window acknowledgement is required")
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cur.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='60s'; "
                    "SET LOCAL idle_in_transaction_session_timeout='60s'")
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (LOCK_KEY,))
        if packed(capture(cur)) != packed(expected):
            raise RuntimeError("catalog drift since inspection")
        if expected["event_triggers"]:
            raise RuntimeError("enabled DDL event triggers require review")
        cur.execute(sql.SQL("ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO {}")
                    .format(sql.Identifier(expected["relation"]["owner"])))
        cur.execute("""SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid()
          AND relation=%s::regclass AND mode='AccessExclusiveLock' AND granted)""", (NAME,))
        if not cur.fetchone()[0]:
            raise RuntimeError("owner action did not retain AccessExclusiveLock")
        if packed(capture(cur)) != packed(expected):
            raise RuntimeError("catalog drift while acquiring relation lock")
        new_definition = expected["definition"] if recover else corrected(expected["definition"])
        if new_definition == expected["definition"] and not recover:
            return False
        cur.execute("DROP MATERIALIZED VIEW public.v_anomaly_flags")  # restrictive native dependency guard
        cur.execute(sql.SQL("CREATE MATERIALIZED VIEW public.v_anomaly_flags USING {} AS {}")
                    .format(sql.Identifier(expected["relation"]["access_method"]), sql.SQL(new_definition)))
        cur.execute(sql.SQL("ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO {}")
                    .format(sql.Identifier(expected["relation"]["owner"])))
        restore_supported_metadata(cur, expected)
        for _, statement, _ in expected["indexes"]:
            cur.execute(statement)
        restore_grants(cur, expected["grants"])
        cur.execute("REFRESH MATERIALIZED VIEW public.v_anomaly_flags")
        cur.execute("SELECT 1 FROM public.v_anomaly_flags LIMIT 1")
        cur.execute("NOTIFY pgrst, 'reload schema'")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn-env", required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("anomaly-flags-snapshot.json"))
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--maintenance-window", default="")
    args = parser.parse_args()
    if args.apply and args.recover:
        parser.error("choose one of --apply or --recover")
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"environment variable {args.dsn_env} is required")
    try:
        with psycopg2.connect(dsn) as conn:
            if args.inspect or not (args.apply or args.recover):
                with conn.cursor() as cur:
                    snapshot = capture(cur)
                wrapper = {"snapshot": snapshot, "digest": fingerprint(snapshot)}
                args.snapshot.write_text(json.dumps(wrapper, sort_keys=True, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
                print(f"inspection snapshot written: {args.snapshot} digest={wrapper['digest']}")
                return 0
            changed = transition(conn, load(args.snapshot), args.maintenance_window, args.recover)
        print("anomaly transition committed" if changed else "anomaly transition no-op")
        return 0
    except Exception as exc:
        print(f"FAIL anomaly transition: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

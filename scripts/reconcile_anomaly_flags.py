"""Guarded PostgreSQL 17 transition for ``public.v_anomaly_flags``.

Inspection is read-only. Apply uses a digest-bound preimage. Recovery uses the
separate committed receipt so the replacement OIDs are guarded independently
from the old semantic definition that recovery restores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

NAME = "public.v_anomaly_flags"
LOCK_KEY = "texas-isd-finances:v_anomaly_flags:v2"
ALLOWED_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}


def packed(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def fingerprint(value: dict) -> str:
    return hashlib.sha256(packed(value)).hexdigest()


def _rows(cur, query: str, params=()) -> list[list[object]]:
    cur.execute(query, params)
    return [list(row) for row in cur]


def capture(cur) -> dict:
    """Capture the complete reviewed catalog surface as inert JSON values."""
    cur.execute("""SELECT current_database(),
      (SELECT oid FROM pg_database WHERE datname=current_database()),
      current_setting('server_version_num'), inet_server_addr()::text,
      inet_server_port(), (SELECT system_identifier::text FROM pg_control_system())""")
    target = list(cur.fetchone())
    cur.execute("""SELECT c.oid,c.reltype,t.typarray,c.xmin::text,pg_get_userbyid(c.relowner),
      c.relpersistence,c.reloptions,c.reltablespace,am.amname,c.relispopulated,
      obj_description(c.oid,'pg_class'),c.relacl::text,pg_get_viewdef(c.oid,true),
      t.typname,at.typname
      FROM pg_class c JOIN pg_type t ON t.oid=c.reltype JOIN pg_type at ON at.oid=t.typarray
      LEFT JOIN pg_am am ON am.oid=c.relam WHERE c.oid=%s::regclass""", (NAME,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"required {NAME} is absent")
    relation = {
        "oid": row[0], "rowtype_oid": row[1], "arraytype_oid": row[2], "xmin": row[3],
        "owner": row[4], "persistence": row[5], "options": row[6], "tablespace_oid": row[7],
        "access_method": row[8], "populated": row[9], "comment": row[10], "acl": row[11],
        "rowtype_name": row[13], "arraytype_name": row[14],
    }
    definition = row[12]
    columns = _rows(cur, """SELECT a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),
      a.attnotnull,col_description(a.attrelid,a.attnum),a.attacl::text,a.attidentity,
      a.attgenerated,a.attstorage,a.attcompression,a.attcollation::regcollation::text,
      a.attstattarget,t.typstorage
      FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
      WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""", (NAME,))
    indexes = _rows(cur, """SELECT ic.oid,ic.relname,pg_get_userbyid(ic.relowner),ic.reloptions,
      ic.reltablespace,am.amname,pg_get_indexdef(ic.oid),obj_description(ic.oid,'pg_class'),
      i.indisunique,i.indisprimary,i.indisvalid,i.indisready
      FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
      LEFT JOIN pg_am am ON am.oid=ic.relam WHERE i.indrelid=%s::regclass ORDER BY ic.relname""", (NAME,))
    rules = _rows(cur, """SELECT oid,rulename,ev_type,ev_enabled,is_instead,
      pg_get_ruledef(oid,true) FROM pg_rewrite WHERE ev_class=%s::regclass ORDER BY rulename""", (NAME,))
    constraints = _rows(cur, """SELECT oid,conname,contype,pg_get_constraintdef(oid,true)
      FROM pg_constraint WHERE conrelid=%s::regclass OR contypid=(SELECT reltype FROM pg_class
      WHERE oid=%s::regclass) ORDER BY conname""", (NAME, NAME))
    types = _rows(cur, """SELECT t.oid,t.typname,t.typtype,t.typcategory,t.typnotnull,t.typacl::text,
      obj_description(t.oid,'pg_type') FROM pg_type t WHERE t.oid IN
      ((SELECT reltype FROM pg_class WHERE oid=%s::regclass),
       (SELECT typarray FROM pg_type WHERE oid=(SELECT reltype FROM pg_class WHERE oid=%s::regclass)))
      ORDER BY t.oid""", (NAME, NAME))
    grants = _rows(cur, """SELECT coalesce(pg_get_userbyid(x.grantee),'PUBLIC'),x.privilege_type,
      x.is_grantable FROM pg_class c CROSS JOIN LATERAL
      aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
      WHERE c.oid=%s::regclass ORDER BY 1,2,3""", (NAME,))
    default_privileges = _rows(cur, """SELECT pg_get_userbyid(d.defaclrole),
      coalesce(n.nspname,''),d.defaclobjtype,d.defaclacl::text
      FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
      WHERE d.defaclrole=(SELECT relowner FROM pg_class WHERE oid=%s::regclass)
      ORDER BY 1,2,3,4""", (NAME,))
    security_labels = _rows(cur, """WITH roots(classoid,objoid) AS (
        SELECT 'pg_class'::regclass::oid,%s::regclass::oid UNION ALL
        SELECT 'pg_type'::regclass::oid,(SELECT reltype FROM pg_class WHERE oid=%s::regclass) UNION ALL
        SELECT 'pg_type'::regclass::oid,(SELECT typarray FROM pg_type
          WHERE oid=(SELECT reltype FROM pg_class WHERE oid=%s::regclass)) UNION ALL
        SELECT 'pg_class'::regclass::oid,indexrelid FROM pg_index WHERE indrelid=%s::regclass)
      SELECT s.classoid::regclass::text,s.objoid,s.objsubid,s.provider,s.label
      FROM pg_seclabel s JOIN roots r USING(classoid,objoid) ORDER BY 1,2,3,4""", (NAME, NAME, NAME, NAME))
    dependencies = _rows(cur, """WITH roots(classid,objid) AS (
        SELECT 'pg_class'::regclass::oid,%s::regclass::oid UNION ALL
        SELECT 'pg_type'::regclass::oid,(SELECT reltype FROM pg_class WHERE oid=%s::regclass) UNION ALL
        SELECT 'pg_type'::regclass::oid,(SELECT typarray FROM pg_type
          WHERE oid=(SELECT reltype FROM pg_class WHERE oid=%s::regclass)) UNION ALL
        SELECT 'pg_class'::regclass::oid,indexrelid FROM pg_index WHERE indrelid=%s::regclass UNION ALL
        SELECT 'pg_rewrite'::regclass::oid,oid FROM pg_rewrite WHERE ev_class=%s::regclass),
      deps AS (SELECT DISTINCT d.* FROM pg_depend d WHERE EXISTS
        (SELECT 1 FROM roots r WHERE (r.classid=d.classid AND r.objid=d.objid)
          OR (r.classid=d.refclassid AND r.objid=d.refobjid)))
      SELECT d.classid::regclass::text,d.objid,d.objsubid,d.refclassid::regclass::text,
        d.refobjid,d.refobjsubid,d.deptype,
        EXISTS(SELECT 1 FROM roots r WHERE r.classid=d.classid AND r.objid=d.objid),
        EXISTS(SELECT 1 FROM roots r WHERE r.classid=d.refclassid AND r.objid=d.refobjid),
        pg_describe_object(d.classid,d.objid,d.objsubid),
        pg_describe_object(d.refclassid,d.refobjid,d.refobjsubid)
      FROM deps d ORDER BY 1,2,3,4,5,6,7""", (NAME, NAME, NAME, NAME, NAME))
    for dep in dependencies:
        obj_owned, ref_owned, ref_class, deptype, obj_description = dep[7], dep[8], dep[3], dep[6], dep[9]
        owned_toast = bool(ref_owned and deptype == "i" and str(obj_description).startswith("toast table "))
        allowed = bool(owned_toast or (obj_owned and (
            ref_owned or not (ref_class == "pg_extension" and deptype == "e")
        )))
        dep.append("owned-internal" if allowed else "unsupported-dependent")
    triggers = _rows(
        cur,
        "SELECT evtname,evtevent,evtenabled,evttags "
        "FROM pg_event_trigger WHERE evtenabled<>'D' ORDER BY evtname",
    )
    return {
        "version": 2, "target": target, "relation": relation, "definition": definition,
        "columns": columns, "indexes": indexes, "rules": rules, "constraints": constraints,
        "types": types, "grants": grants, "default_privileges": default_privileges,
        "security_labels": security_labels, "dependencies": dependencies,
        "event_triggers": triggers,
    }


def validate_supported(snapshot: dict) -> None:
    if snapshot.get("version") != 2:
        raise RuntimeError("unsupported inspection snapshot version")
    relation = snapshot["relation"]
    if relation["persistence"] != "p" or relation["tablespace_oid"] != 0:
        raise RuntimeError("nondefault persistence or tablespace requires a reviewed transition")
    if relation["access_method"] != "heap":
        raise RuntimeError("non-heap access method requires a reviewed transition")
    if snapshot["event_triggers"]:
        raise RuntimeError("enabled DDL event triggers require review")
    if snapshot["security_labels"]:
        raise RuntimeError("security labels require a reviewed transition")
    if snapshot["constraints"]:
        raise RuntimeError("materialized-view constraints require a reviewed transition")
    unsupported = [row for row in snapshot["dependencies"] if row[-1] != "owned-internal"]
    if unsupported:
        raise RuntimeError(f"unsupported dependency must be removed or reviewed before DROP: {unsupported[0][-3:-1]}")
    for column in snapshot["columns"]:
        _, name, _, notnull, _, acl, identity, generated, storage, compression, _, stats, default_storage = column
        if acl:
            raise RuntimeError(f"column ACL on {name} requires a reviewed transition")
        if notnull or identity or generated or compression or stats not in (None, -1) or storage != default_storage:
            raise RuntimeError(
                f"special column property on {name} requires a reviewed transition "
                f"(notnull={notnull!r}, identity={identity!r}, generated={generated!r}, "
                f"storage={storage!r}/{default_storage!r}, compression={compression!r}, stats={stats!r})"
            )
    for _, _, type_kind, _, notnull, acl, _ in snapshot["types"]:
        if type_kind not in {"c", "b"} or notnull or acl:
            raise RuntimeError("special row/array type metadata requires a reviewed transition")
    for index in snapshot["indexes"]:
        if index[3] or index[4] != 0 or index[5] not in {"btree"} or not index[10] or not index[11]:
            raise RuntimeError(f"unsupported index metadata on {index[1]}")


def make_wrapper(kind: str, value: dict) -> dict:
    return {"kind": kind, "value": value, "digest": fingerprint(value)}


def load_wrapper(path: Path, kind: str) -> dict:
    wrapper = json.loads(path.read_text(encoding="utf-8"))
    value = wrapper.get("value")
    if wrapper.get("kind") != kind or not isinstance(value, dict) or wrapper.get("digest") != fingerprint(value):
        raise RuntimeError(f"invalid or modified {kind}")
    return value


def corrected(definition: str) -> str:
    result = definition.replace("(total_revenue - prev_revenue) / prev_revenue",
                                "(total_revenue - prev_revenue)::numeric / prev_revenue")
    result = result.replace("(total_spend - prev_spend) / prev_spend",
                            "(total_spend - prev_spend)::numeric / prev_spend")
    already = "::numeric / prev_revenue" in definition and "::numeric / prev_spend" in definition
    if result == definition and not already:
        raise RuntimeError("reviewed anomaly expressions were not found")
    return result


def reviewed_definition_pair(preimage: str, committed: str) -> bool:
    """Prove PG's reparsed definition differs only at the two reviewed ratios."""
    patterns = {
        "__REVENUE_RATIO__": (
            r"\(\(total_revenue - prev_revenue\) / prev_revenue\)::numeric",
            r"\(\(total_revenue - prev_revenue\)::numeric / prev_revenue::numeric\)",
        ),
        "__SPEND_RATIO__": (
            r"\(\(total_spend - prev_spend\) / prev_spend\)::numeric",
            r"\(\(total_spend - prev_spend\)::numeric / prev_spend::numeric\)",
        ),
    }
    old_normalized, new_normalized = preimage, committed
    for marker, (old_pattern, new_pattern) in patterns.items():
        old_normalized, old_count = re.subn(old_pattern, marker, old_normalized, count=1)
        new_normalized, new_count = re.subn(new_pattern, marker, new_normalized, count=1)
        if old_count != 1 or new_count != 1:
            return False
    def squash(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().removesuffix(";")

    return squash(old_normalized) == squash(new_normalized)


def restore_grants(cur, grants: list[list[object]], owner: str) -> None:
    current = _rows(cur, """SELECT DISTINCT coalesce(pg_get_userbyid(x.grantee),'PUBLIC')
      FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
      WHERE c.oid=%s::regclass""", (NAME,))
    grantees = {str(row[0]) for row in current} | {str(row[0]) for row in grants}
    for grantee in sorted(grantees - {owner}):
        role = sql.SQL("PUBLIC") if grantee == "PUBLIC" else sql.Identifier(grantee)
        cur.execute(sql.SQL("REVOKE ALL PRIVILEGES ON TABLE public.v_anomaly_flags FROM {}").format(role))
    for grantee, privilege, grantable in grants:
        if grantee == owner:
            continue
        if privilege not in ALLOWED_PRIVILEGES:
            raise RuntimeError(f"unsupported privilege {privilege}")
        role = sql.SQL("PUBLIC") if grantee == "PUBLIC" else sql.Identifier(str(grantee))
        cur.execute(sql.SQL("GRANT {} ON TABLE public.v_anomaly_flags TO {}{}").format(
            sql.SQL(str(privilege)), role, sql.SQL(" WITH GRANT OPTION") if grantable else sql.SQL("")))


def restore_metadata(cur, source: dict) -> None:
    relation = source["relation"]
    for option in relation["options"] or []:
        match = re.fullmatch(r"fillfactor=(\d{1,3})", option)
        if not match or not 10 <= int(match.group(1)) <= 100:
            raise RuntimeError(f"unsupported materialized-view reloption: {option!r}")
        cur.execute(sql.SQL("ALTER MATERIALIZED VIEW public.v_anomaly_flags SET (fillfactor={})")
                    .format(sql.Literal(int(match.group(1)))))
    if relation["comment"] is not None:
        cur.execute("COMMENT ON MATERIALIZED VIEW public.v_anomaly_flags IS %s", (relation["comment"],))
    for column in source["columns"]:
        if column[4] is not None:
            cur.execute(sql.SQL("COMMENT ON COLUMN public.v_anomaly_flags.{} IS %s")
                        .format(sql.Identifier(column[1])), (column[4],))
    for type_row in source["types"]:
        if type_row[6] is not None:
            cur.execute(sql.SQL("COMMENT ON TYPE public.{} IS %s")
                        .format(sql.Identifier(type_row[1])), (type_row[6],))


def metadata_contract(snapshot: dict) -> dict:
    relation = snapshot["relation"]
    return {
        "relation": {key: relation[key] for key in (
            "owner", "persistence", "options", "tablespace_oid", "access_method", "populated", "comment",
            "rowtype_name", "arraytype_name")},
        "columns": snapshot["columns"],
        "indexes": [row[1:] for row in snapshot["indexes"]],
        "rules": [row[1:5] for row in snapshot["rules"]],
        "types": [row[1:] for row in snapshot["types"]],
        "grants": snapshot["grants"],
        "default_privileges": snapshot["default_privileges"],
        "security_labels": snapshot["security_labels"],
    }


def transition(conn, guard: dict, metadata_source: dict, target_definition: str,
               ack: str, *, failure_at: str | None = None, on_stage=None,
               lock_timeout: str = "1500ms", statement_timeout: str = "15s") -> tuple[bool, dict]:
    if not ack:
        raise RuntimeError("--maintenance-window acknowledgement is required")
    validate_supported(guard)
    validate_supported(metadata_source)
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cur.execute("SET LOCAL lock_timeout=%s; SET LOCAL statement_timeout=%s; "
                    "SET LOCAL idle_in_transaction_session_timeout=%s",
                    (lock_timeout, statement_timeout, statement_timeout))
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (LOCK_KEY,))
        if packed(capture(cur)) != packed(guard):
            raise RuntimeError("catalog drift since inspection")
        if on_stage:
            on_stage("before_owner_lock")
        cur.execute(sql.SQL("ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO {}")
                    .format(sql.Identifier(guard["relation"]["owner"])))
        cur.execute("""SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid()
          AND relation=%s::regclass AND mode='AccessExclusiveLock' AND granted)""", (NAME,))
        if not cur.fetchone()[0]:
            raise RuntimeError("owner action did not retain AccessExclusiveLock")
        if on_stage:
            on_stage("after_lock")
        if failure_at == "after_lock":
            raise RuntimeError("injected failure after lock")
        if packed(capture(cur)) != packed(guard):
            raise RuntimeError("catalog drift while acquiring relation lock")
        if target_definition == guard["definition"]:
            return False, guard
        if on_stage:
            on_stage("before_drop")
        cur.execute("DROP MATERIALIZED VIEW public.v_anomaly_flags")
        if failure_at == "after_drop":
            raise RuntimeError("injected failure after DROP")
        create_definition = target_definition.rstrip().removesuffix(";")
        cur.execute(sql.SQL("CREATE MATERIALIZED VIEW public.v_anomaly_flags USING {} AS {} WITH NO DATA")
                    .format(sql.Identifier(metadata_source["relation"]["access_method"]), sql.SQL(create_definition)))
        if on_stage:
            on_stage("after_create")
        if failure_at == "after_create":
            raise RuntimeError("injected failure after CREATE")
        cur.execute(sql.SQL("ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO {}")
                    .format(sql.Identifier(metadata_source["relation"]["owner"])))
        restore_metadata(cur, metadata_source)
        for index in metadata_source["indexes"]:
            cur.execute(index[6])
            if index[7] is not None:
                cur.execute(sql.SQL("COMMENT ON INDEX public.{} IS %s").format(sql.Identifier(index[1])), (index[7],))
        restore_grants(cur, metadata_source["grants"], metadata_source["relation"]["owner"])
        if metadata_source["relation"]["populated"]:
            cur.execute("REFRESH MATERIALIZED VIEW public.v_anomaly_flags")
        if failure_at == "after_restore":
            raise RuntimeError("injected failure after metadata restoration")
        after = capture(cur)
        validate_supported(after)
        actual_contract = metadata_contract(after)
        expected_contract = metadata_contract(metadata_source)
        if actual_contract != expected_contract:
            differing = [key for key in expected_contract if actual_contract[key] != expected_contract[key]]
            raise RuntimeError(f"restored metadata differs from reviewed contract: {differing}")
        cur.execute("""SELECT count(*) FROM public.v_anomaly_flags WHERE
          revenue_drop_flag IS DISTINCT FROM coalesce((prev_revenue > 0 AND
            (total_revenue-prev_revenue)::numeric/prev_revenue < -0.15),false)
          OR spend_spike_flag IS DISTINCT FROM coalesce((prev_spend > 0 AND
            (total_spend-prev_spend)::numeric/prev_spend > 0.20 AND
            abs(coalesce(enrollment,0)-coalesce(prev_enrollment,0)) < 10),false)""")
        if cur.fetchone()[0]:
            raise RuntimeError("anomaly arithmetic assertion failed")
        if failure_at == "after_assertions":
            raise RuntimeError("injected failure after assertions")
        cur.execute("NOTIFY pgrst, 'reload schema'")
        return True, after


def receipt_path(snapshot_path: Path) -> Path:
    return snapshot_path.with_suffix(".receipt.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn-env", required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("anomaly-flags-snapshot.json"))
    parser.add_argument("--receipt", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--inspect", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--recover", action="store_true")
    parser.add_argument("--maintenance-window", default="")
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"environment variable {args.dsn_env} is required")
    receipt_file = args.receipt or receipt_path(args.snapshot)
    try:
        if args.inspect or not (args.apply or args.recover):
            with psycopg2.connect(dsn) as conn:
                conn.set_session(readonly=True, autocommit=False)
                with conn.cursor() as cur:
                    snapshot = capture(cur)
                conn.rollback()
            args.snapshot.write_text(json.dumps(make_wrapper("anomaly-preimage", snapshot),
                                                sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8", newline="\n")
            print(f"inspection snapshot written: {args.snapshot} digest={fingerprint(snapshot)}")
            return 0

        with psycopg2.connect(dsn) as conn:
            if args.apply:
                preimage = load_wrapper(args.snapshot, "anomaly-preimage")
                changed, _ = transition(conn, preimage, preimage, corrected(preimage["definition"]),
                                        args.maintenance_window)
                conn.commit()
                with conn.cursor() as cur:
                    committed = capture(cur)
                if changed:
                    receipt = {"preimage": preimage, "committed": committed,
                               "preimage_digest": fingerprint(preimage),
                               "committed_digest": fingerprint(committed)}
                    receipt_file.write_text(json.dumps(make_wrapper("anomaly-transition-receipt", receipt),
                                                       sort_keys=True, indent=2) + "\n",
                                            encoding="utf-8", newline="\n")
            else:
                receipt = load_wrapper(receipt_file, "anomaly-transition-receipt")
                if receipt.get("preimage_digest") != fingerprint(receipt["preimage"]) or \
                        receipt.get("committed_digest") != fingerprint(receipt["committed"]):
                    raise RuntimeError("invalid nested receipt digests")
                if not reviewed_definition_pair(
                    receipt["preimage"]["definition"], receipt["committed"]["definition"]
                ):
                    raise RuntimeError("receipt semantic definitions do not form a reviewed repair pair")
                if metadata_contract(receipt["preimage"]) != metadata_contract(receipt["committed"]):
                    raise RuntimeError("receipt metadata contracts differ")
                if receipt["preimage"]["target"] != receipt["committed"]["target"]:
                    raise RuntimeError("receipt target identity differs")
                changed, _ = transition(conn, receipt["committed"], receipt["preimage"],
                                        receipt["preimage"]["definition"], args.maintenance_window)
                conn.commit()
        print("anomaly transition committed" if changed else "anomaly transition no-op")
        if changed and args.apply:
            print(f"committed receipt written: {receipt_file}")
        return 0
    except Exception as exc:
        print(f"FAIL anomaly transition: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

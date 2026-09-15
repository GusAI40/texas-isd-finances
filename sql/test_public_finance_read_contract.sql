-- Run with psql -v ON_ERROR_STOP=1 -f sql/test_public_finance_read_contract.sql
-- Read-only regression: mutation probes use WHERE false and must be denied.
-- The transaction is rolled back. Run as an administrator able to SET ROLE.
BEGIN;
DO $$
DECLARE
  role_name text;
  object_name text;
  actual_count bigint;
  expected_count bigint;
  baseline jsonb := '{}'::jsonb;
  objects text[] := ARRAY['v_finance_summary','v_spending_detail',
    'v_spending_breakdown','district_similarity','v_anomaly_flags'];
BEGIN
  FOREACH object_name IN ARRAY objects LOOP
    EXECUTE format('SELECT count(*) FROM public.%I',object_name) INTO expected_count;
    baseline := baseline || jsonb_build_object(object_name,expected_count);
  END LOOP;
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
    EXECUTE format('SET LOCAL ROLE %I',role_name);
    FOREACH object_name IN ARRAY objects LOOP
      IF NOT has_table_privilege(current_user,'public.'||object_name,'SELECT')
         OR has_table_privilege(current_user,'public.'||object_name,
           'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') THEN
        RAISE EXCEPTION '% is not SELECT-only on %',current_user,object_name;
      END IF;
      EXECUTE format('SELECT count(*) FROM public.%I',object_name) INTO actual_count;
      IF actual_count <> (baseline->>object_name)::bigint THEN
        RAISE EXCEPTION 'Public read coverage changed for % on %',current_user,object_name;
      END IF;
      -- Materialized views reject DML by shape; ACL checks above test their grants.
      IF object_name <> 'v_anomaly_flags' THEN
        BEGIN
          EXECUTE format('DELETE FROM public.%I WHERE false',object_name);
          RAISE EXCEPTION 'Unexpected DELETE permission for % on %',current_user,object_name;
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
      END IF;
    END LOOP;
    IF has_table_privilege(current_user,'public.texas_school_finance','SELECT') THEN
      RAISE EXCEPTION 'Base finance table unexpectedly exposed to %',current_user;
    END IF;
    RESET ROLE;
  END LOOP;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.district_similarity'::regclass) THEN
    RAISE EXCEPTION 'district_similarity RLS disabled';
  END IF;
END $$;
ROLLBACK;

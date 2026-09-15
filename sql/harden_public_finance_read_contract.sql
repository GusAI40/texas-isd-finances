-- Production repair applied 2026-09-15 through Supabase migration
-- harden_public_finance_read_contract on zwhvabkvrexphlskubog.
-- Re-run after any schema bootstrap that recreates views or their grants.
-- Preserve the intentional public read-only projections in create_tables.sql.
-- Do NOT switch the existing views to security_invoker without redesigning
-- their access contract: public callers and nlp_reader intentionally have no
-- direct base-table privileges. This script changes no rows or view definitions.
BEGIN;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM (VALUES
      ('v_finance_summary','v'),('v_spending_detail','v'),
      ('v_spending_breakdown','v'),('v_anomaly_flags','m'),
      ('district_similarity','r')
    ) AS expected(name,kind)
    LEFT JOIN pg_class c ON c.oid=to_regclass('public.'||expected.name)
    WHERE c.oid IS NULL OR c.relkind::text<>expected.kind
  ) THEN
    RAISE EXCEPTION 'Unexpected finance object shape; refusing ACL repair';
  END IF;
END $$;
REVOKE ALL PRIVILEGES ON TABLE public.v_finance_summary, public.v_spending_detail,
 public.v_spending_breakdown, public.v_anomaly_flags, public.district_similarity
 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.v_finance_summary, public.v_spending_detail,
 public.v_spending_breakdown, public.v_anomaly_flags, public.district_similarity
 TO anon, authenticated;
ALTER TABLE public.district_similarity ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public'
      AND tablename='district_similarity' AND policyname='district_similarity_public_read') THEN
    CREATE POLICY district_similarity_public_read ON public.district_similarity
      FOR SELECT TO anon, authenticated USING (true);
  END IF;
END $$;
NOTIFY pgrst, 'reload schema';
COMMIT;

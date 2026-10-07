-- Reviewed public-read contract, retained here for controlled disposable testing.
-- Production application was separately recorded on 2026-09-15; do not run it
-- against a target until its identity and current grants are independently verified.
BEGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC, anon, authenticated, nlp_reader;
GRANT USAGE ON SCHEMA public TO anon, authenticated, nlp_reader;
REVOKE ALL ON public.texas_school_finance FROM PUBLIC, anon, authenticated, nlp_reader;
REVOKE ALL ON public.v_finance_summary, public.v_spending_detail, public.v_spending_breakdown, public.v_district_similarity, public.v_anomaly_flags FROM PUBLIC, anon, authenticated, nlp_reader;
GRANT SELECT ON public.v_finance_summary, public.v_spending_detail, public.v_spending_breakdown, public.v_district_similarity, public.v_anomaly_flags TO anon, authenticated;
GRANT SELECT ON public.v_finance_summary, public.v_anomaly_flags TO nlp_reader;
COMMIT;

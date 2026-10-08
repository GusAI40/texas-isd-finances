-- Exceptional post-commit compatibility recovery only: restores known old
-- integer arithmetic while preserving the 30-column contract and dependencies.
-- This is not a correctness repair and requires an incident decision.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $$
DECLARE
  actual text[];
  types text[];
  definition text;
  saved_reloptions text[];
BEGIN
  SELECT array_agg(column_name ORDER BY ordinal_position),
         array_agg(data_type ORDER BY ordinal_position)
    INTO actual, types
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'v_finance_summary';
  IF actual IS DISTINCT FROM ARRAY[
       'district_number','district_name','year','total_revenue','total_spend','enrollment',
       'spend_per_student','revenue_per_student','instruction_spend','debt_service',
       'capital_projects','operating_spend','library_media_spend','curriculum_staff_dev_spend',
       'instructional_leadership_spend','campus_admin_spend','counseling_spend','social_work_spend',
       'health_services_spend','transportation_spend','food_service_spend','extracurricular_spend',
       'general_admin_spend','plant_maintenance_spend','security_spend','data_processing_spend',
       'community_services_spend','payroll_spend','contracted_services_spend','supplies_spend']
     OR types IS DISTINCT FROM ARRAY['text','text'] || array_fill('bigint'::text, ARRAY[4])
       || ARRAY['numeric','numeric'] || array_fill('bigint'::text, ARRAY[22]) THEN
    RAISE EXCEPTION 'unexpected corrected summary contract: %, %', actual, types;
  END IF;
  SELECT pg_get_viewdef('public.v_finance_summary'::regclass, true), c.reloptions
    INTO definition, saved_reloptions
    FROM pg_class c WHERE c.oid = 'public.v_finance_summary'::regclass;
  IF definition !~ 'all_funds_total_disbursements[^/]*::numeric\s*/\s*fall_survey_enrollment'
     OR definition !~ 'all_funds_total_operating_revenue[^/]*::numeric\s*/\s*fall_survey_enrollment' THEN
    RAISE EXCEPTION 'summary is not the reviewed corrected definition';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(coalesce(saved_reloptions, ARRAY[]::text[])) option_value
     WHERE option_value !~ '^(security_barrier=(true|false)|security_invoker=(true|false)|check_option=(local|cascaded))$'
  ) THEN
    RAISE EXCEPTION 'unsupported v_finance_summary option: %', saved_reloptions;
  END IF;
  PERFORM set_config(
    'txisd.summary_reloptions', coalesce(array_to_string(saved_reloptions, ','), ''), true
  );
END $$;
CREATE OR REPLACE VIEW public.v_finance_summary AS
SELECT district_number,district_name,year,all_funds_total_operating_revenue AS total_revenue,
 all_funds_total_disbursements AS total_spend,fall_survey_enrollment AS enrollment,
 CASE WHEN fall_survey_enrollment>0 THEN round((all_funds_total_disbursements/fall_survey_enrollment)::numeric,2) END AS spend_per_student,
 CASE WHEN fall_survey_enrollment>0 THEN round((all_funds_total_operating_revenue/fall_survey_enrollment)::numeric,2) END AS revenue_per_student,
 all_funds_instruction_transfer_expend_fct11_95 AS instruction_spend,all_funds_debt_service_object_6500_for_td AS debt_service,
 all_funds_capital_projects_object_6600_for_td AS capital_projects,all_funds_total_operating_expenditures_by_obj AS operating_spend,
 all_funds_instruc_resource_media_service_exp_fct12 AS library_media_spend,all_funds_curriculum_staff_development_exp_fct13 AS curriculum_staff_dev_spend,
 all_funds_instruc_leadership_expend_fct21 AS instructional_leadership_spend,all_funds_campus_administration_expend_fct23 AS campus_admin_spend,
 all_funds_guidance_counseling_services_exp_fct31 AS counseling_spend,all_funds_social_work_services_exp_fct32 AS social_work_spend,
 all_funds_health_services_exp_fct33 AS health_services_spend,all_funds_transportation_expenditures_fct34 AS transportation_spend,
 all_funds_food_service_expenditures_fct35 AS food_service_spend,all_funds_extracurricular_expenditures_fct36 AS extracurricular_spend,
 all_funds_general_administrat_expend_fct41_92 AS general_admin_spend,all_funds_plant_maintenance_opera_expend_fct51 AS plant_maintenance_spend,
 all_funds_security_monitoring_service_expend_fct52 AS security_spend,all_funds_data_processing_services_expend_fct53 AS data_processing_spend,
 all_funds_community_services_fct61 AS community_services_spend,all_funds_total_payroll_expenditures AS payroll_spend,
 all_funds_total_professional_contracted_services_expenditure AS contracted_services_spend,
 all_funds_total_supplies_materials_expenditures AS supplies_spend
FROM public.texas_school_finance;
DO $$
DECLARE saved text := current_setting('txisd.summary_reloptions', true);
BEGIN
  IF saved IS NOT NULL AND saved <> '' THEN
    EXECUTE 'ALTER VIEW public.v_finance_summary SET (' || saved || ')';
  END IF;
END $$;
REFRESH MATERIALIZED VIEW public.v_anomaly_flags;
NOTIFY pgrst, 'reload schema';
COMMIT;

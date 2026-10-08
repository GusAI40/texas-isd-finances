-- Additive public.v_finance_summary repair.  It has one reviewed 30-column
-- contract and deliberately does not derive a replacement definition from text.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $$
DECLARE
  actual text[];
  types text[];
  expected_12 constant text[] := ARRAY[
    'district_number','district_name','year','total_revenue','total_spend','enrollment',
    'spend_per_student','revenue_per_student','instruction_spend','debt_service',
    'capital_projects','operating_spend'];
  expected_30 constant text[] := expected_12 || ARRAY[
    'library_media_spend','curriculum_staff_dev_spend','instructional_leadership_spend',
    'campus_admin_spend','counseling_spend','social_work_spend','health_services_spend',
    'transportation_spend','food_service_spend','extracurricular_spend','general_admin_spend',
    'plant_maintenance_spend','security_spend','data_processing_spend','community_services_spend',
    'payroll_spend','contracted_services_spend','supplies_spend'];
  expected_types_12 constant text[] := ARRAY[
    'text','text','bigint','bigint','bigint','bigint','numeric','numeric',
    'bigint','bigint','bigint','bigint'];
  expected_types_30 constant text[] := expected_types_12 || ARRAY[
    'bigint','bigint','bigint','bigint','bigint','bigint','bigint','bigint','bigint',
    'bigint','bigint','bigint','bigint','bigint','bigint','bigint','bigint','bigint'];
  required_base constant text[] := ARRAY[
    'district_number','district_name','year','all_funds_total_operating_revenue',
    'all_funds_total_disbursements','fall_survey_enrollment',
    'all_funds_instruction_transfer_expend_fct11_95',
    'all_funds_debt_service_object_6500_for_td','all_funds_capital_projects_object_6600_for_td',
    'all_funds_total_operating_expenditures_by_obj',
    'all_funds_instruc_resource_media_service_exp_fct12',
    'all_funds_curriculum_staff_development_exp_fct13','all_funds_instruc_leadership_expend_fct21',
    'all_funds_campus_administration_expend_fct23','all_funds_guidance_counseling_services_exp_fct31',
    'all_funds_social_work_services_exp_fct32','all_funds_health_services_exp_fct33',
    'all_funds_transportation_expenditures_fct34','all_funds_food_service_expenditures_fct35',
    'all_funds_extracurricular_expenditures_fct36','all_funds_general_administrat_expend_fct41_92',
    'all_funds_plant_maintenance_opera_expend_fct51',
    'all_funds_security_monitoring_service_expend_fct52',
    'all_funds_data_processing_services_expend_fct53','all_funds_community_services_fct61',
    'all_funds_total_payroll_expenditures',
    'all_funds_total_professional_contracted_services_expenditure',
    'all_funds_total_supplies_materials_expenditures'];
  base_actual text[];
  base_types text[];
  saved_reloptions text[];
BEGIN
  SELECT array_agg(column_name ORDER BY ordinal_position),
         array_agg(data_type ORDER BY ordinal_position) INTO actual, types
  FROM information_schema.columns WHERE table_schema='public' AND table_name='v_finance_summary';
  IF NOT ((actual = expected_12 AND types = expected_types_12)
          OR (actual = expected_30 AND types = expected_types_30)) THEN
    RAISE EXCEPTION 'unexpected v_finance_summary contract: %, %', actual, types;
  END IF;

  SELECT c.reloptions INTO saved_reloptions
    FROM pg_class c WHERE c.oid = 'public.v_finance_summary'::regclass;
  IF EXISTS (
    SELECT 1 FROM unnest(coalesce(saved_reloptions, ARRAY[]::text[])) option_value
     WHERE option_value !~ '^(security_barrier=(true|false)|security_invoker=(true|false)|check_option=(local|cascaded))$'
  ) THEN
    RAISE EXCEPTION 'unsupported v_finance_summary option: %', saved_reloptions;
  END IF;
  PERFORM set_config(
    'txisd.summary_reloptions', coalesce(array_to_string(saved_reloptions, ','), ''), true
  );

  SELECT array_agg(required_name ORDER BY ordinal),
         array_agg(c.data_type ORDER BY ordinal)
    INTO base_actual, base_types
    FROM unnest(required_base) WITH ORDINALITY AS required(required_name, ordinal)
    LEFT JOIN information_schema.columns c
      ON c.table_schema = 'public' AND c.table_name = 'texas_school_finance'
     AND c.column_name = required.required_name;
  IF base_actual IS DISTINCT FROM required_base
     OR base_types IS DISTINCT FROM ARRAY['text','text'] || array_fill('bigint'::text, ARRAY[26]) THEN
    RAISE EXCEPTION 'unexpected texas_school_finance required-column contract: %, %',
      base_actual, base_types;
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM pg_class m
      JOIN pg_namespace n ON n.oid = m.relnamespace
      JOIN pg_rewrite r ON r.ev_class = m.oid
      JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass AND d.objid = r.oid
     WHERE n.nspname = 'public' AND m.relname = 'v_anomaly_flags' AND m.relkind = 'm'
       AND d.refobjid = 'public.v_finance_summary'::regclass
  ) THEN
    RAISE EXCEPTION 'required dependent anomaly matview absent or unrelated';
  END IF;
END $$;
CREATE OR REPLACE VIEW public.v_finance_summary AS
SELECT district_number,district_name,year,all_funds_total_operating_revenue AS total_revenue,
 all_funds_total_disbursements AS total_spend,fall_survey_enrollment AS enrollment,
 CASE WHEN fall_survey_enrollment>0 THEN round(all_funds_total_disbursements::numeric/fall_survey_enrollment,2) END AS spend_per_student,
 CASE WHEN fall_survey_enrollment>0 THEN round(all_funds_total_operating_revenue::numeric/fall_survey_enrollment,2) END AS revenue_per_student,
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
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM public.v_finance_summary WHERE (enrollment IS NULL OR enrollment<=0) AND (spend_per_student IS NOT NULL OR revenue_per_student IS NOT NULL)) THEN
  RAISE EXCEPTION 'invalid denominator result';
 END IF;
END $$;
NOTIFY pgrst, 'reload schema';
COMMIT;

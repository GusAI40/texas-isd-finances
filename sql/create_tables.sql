-- Post-import schema setup for texas_school_finance.
--
-- ORDER MATTERS: run scripts/import_to_supabase.py FIRST. The import creates
-- the base table with all 140 columns straight from the cleaned TEA data
-- (fiscal years 2009-2025). This script then adds the primary key, indexes,
-- public views, anomaly materialized view, row-level security, and grants.

-- Primary key (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'texas_school_finance_pkey'
    ) THEN
        ALTER TABLE public.texas_school_finance
            ALTER COLUMN district_number SET NOT NULL,
            ALTER COLUMN year SET NOT NULL,
            ADD CONSTRAINT texas_school_finance_pkey PRIMARY KEY (district_number, year);
    END IF;
END $$;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tex_fin_year ON public.texas_school_finance (year);
CREATE INDEX IF NOT EXISTS idx_tex_fin_district ON public.texas_school_finance (district_number);
CREATE INDEX IF NOT EXISTS idx_tex_fin_district_name ON public.texas_school_finance (district_name);

-- Create summary view for public access
CREATE OR REPLACE VIEW public.v_finance_summary AS
SELECT
    district_number,
    district_name,
    year,
    all_funds_total_operating_revenue AS total_revenue,
    all_funds_total_disbursements AS total_spend,
    fall_survey_enrollment AS enrollment,
    CASE
        WHEN fall_survey_enrollment > 0
        THEN ROUND((all_funds_total_disbursements / fall_survey_enrollment)::numeric, 2)
        ELSE NULL
    END AS spend_per_student,
    CASE
        WHEN fall_survey_enrollment > 0
        THEN ROUND((all_funds_total_operating_revenue / fall_survey_enrollment)::numeric, 2)
        ELSE NULL
    END AS revenue_per_student,
    all_funds_instruction_transfer_expend_fct11_95 AS instruction_spend,
    all_funds_debt_service_object_6500_for_td AS debt_service,
    all_funds_capital_projects_object_6600_for_td AS capital_projects,
    -- Operating spend, separately from total disbursements. total_spend
    -- includes bond-funded construction and debt service, so comparing it
    -- with OPERATING revenue calls every fast-growing district a deficit:
    -- Argyle ISD read "Deficit, $63.9M vs $193.8M" in a year its operations
    -- ran a $532k surplus — the $130M gap was voter-approved buildings.
    all_funds_total_operating_expenditures_by_obj AS operating_spend,
    -- The other fourteen PEIMS function codes. They were in this table from
    -- the first import (to_sql writes all 140 CSV columns) and reachable by
    -- nobody: the view exposed one of the sixteen, and nlp_reader is granted
    -- SELECT on this view and v_anomaly_flags and nothing else. So the agent
    -- could report what a district spent in total and could not report what it
    -- spent on buses. A coverage simulation on 2026-08-23 measured that single
    -- omission at 8.9% of realistic questions.
    --
    -- Appended at the END on purpose: CREATE OR REPLACE VIEW permits adding
    -- columns but not reordering or renaming existing ones, so this stays a
    -- replace rather than a drop-and-recreate — which would silently discard
    -- the GRANT to nlp_reader.
    all_funds_instruc_resource_media_service_exp_fct12 AS library_media_spend,
    all_funds_curriculum_staff_development_exp_fct13 AS curriculum_staff_dev_spend,
    all_funds_instruc_leadership_expend_fct21 AS instructional_leadership_spend,
    all_funds_campus_administration_expend_fct23 AS campus_admin_spend,
    all_funds_guidance_counseling_services_exp_fct31 AS counseling_spend,
    all_funds_social_work_services_exp_fct32 AS social_work_spend,
    all_funds_health_services_exp_fct33 AS health_services_spend,
    all_funds_transportation_expenditures_fct34 AS transportation_spend,
    all_funds_food_service_expenditures_fct35 AS food_service_spend,
    all_funds_extracurricular_expenditures_fct36 AS extracurricular_spend,
    all_funds_general_administrat_expend_fct41_92 AS general_admin_spend,
    all_funds_plant_maintenance_opera_expend_fct51 AS plant_maintenance_spend,
    all_funds_security_monitoring_service_expend_fct52 AS security_spend,
    all_funds_data_processing_services_expend_fct53 AS data_processing_spend,
    all_funds_community_services_fct61 AS community_services_spend,
    -- What the money was bought AS, rather than what it was bought FOR.
    all_funds_total_payroll_expenditures AS payroll_spend,
    all_funds_total_professional_contracted_services_expenditure AS contracted_services_spend,
    all_funds_total_supplies_materials_expenditures AS supplies_spend
FROM public.texas_school_finance;

-- Create materialized view for anomaly detection
DROP MATERIALIZED VIEW IF EXISTS public.v_anomaly_flags;
CREATE MATERIALIZED VIEW public.v_anomaly_flags AS
WITH finance_changes AS (
    SELECT
        district_number,
        district_name,
        year,
        total_revenue,
        total_spend,
        enrollment,
        spend_per_student,
        -- Calculate year-over-year changes
        LAG(total_revenue) OVER (PARTITION BY district_number ORDER BY year) AS prev_revenue,
        LAG(total_spend) OVER (PARTITION BY district_number ORDER BY year) AS prev_spend,
        LAG(enrollment) OVER (PARTITION BY district_number ORDER BY year) AS prev_enrollment,
        LAG(spend_per_student) OVER (PARTITION BY district_number ORDER BY year) AS prev_spend_per_student
    FROM v_finance_summary
)
SELECT
    district_number,
    district_name,
    year,
    -- Revenue drop > 15%
    CASE
        WHEN prev_revenue > 0 AND (total_revenue - prev_revenue) / prev_revenue < -0.15
        THEN true ELSE false
    END AS revenue_drop_flag,
    -- Spending increase > 20% with flat enrollment
    CASE
        WHEN prev_spend > 0
        AND (total_spend - prev_spend) / prev_spend > 0.20
        AND ABS(COALESCE(enrollment, 0) - COALESCE(prev_enrollment, 0)) < 10
        THEN true ELSE false
    END AS spend_spike_flag,
    -- Per-student spending increase > 15%
    CASE
        WHEN prev_spend_per_student > 0
        AND spend_per_student > 0
        AND (spend_per_student - prev_spend_per_student) / prev_spend_per_student > 0.15
        THEN true ELSE false
    END AS per_student_spike_flag,
    -- Enrollment decline > 10%
    CASE
        WHEN prev_enrollment > 0
        AND enrollment > 0
        AND (enrollment - prev_enrollment)::float / prev_enrollment < -0.10
        THEN true ELSE false
    END AS enrollment_decline_flag,
    -- Include the actual values for context
    total_revenue,
    prev_revenue,
    total_spend,
    prev_spend,
    enrollment,
    prev_enrollment,
    spend_per_student,
    prev_spend_per_student
FROM finance_changes
WHERE year > (SELECT MIN(year) FROM v_finance_summary); -- Exclude first year (no previous data)

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_anomaly_flags_district ON public.v_anomaly_flags (district_number);
CREATE INDEX IF NOT EXISTS idx_anomaly_flags_year ON public.v_anomaly_flags (year);

-- Lock down the base table: revoke direct access and enable row-level
-- security with no policies, so API roles can only read through the views.
REVOKE ALL ON public.texas_school_finance FROM anon, authenticated;
ALTER TABLE public.texas_school_finance ENABLE ROW LEVEL SECURITY;

-- Grant read-only access to the public views
GRANT SELECT ON public.v_finance_summary TO anon, authenticated;
GRANT SELECT ON public.v_anomaly_flags TO anon, authenticated;

-- After importing new data, re-run this whole file (the materialized view
-- is rebuilt), or just refresh:
--   REFRESH MATERIALIZED VIEW public.v_anomaly_flags;

-- Also run sql/create_nlp_usage.sql. It creates the cross-instance call
-- counter that bounds /query's OpenAI spend. Without that table the API
-- still runs — it logs a warning and falls back to per-instance counters,
-- which on serverless is not a real ceiling at all. See the header of that
-- file for why.

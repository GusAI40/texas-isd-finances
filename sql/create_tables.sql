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
    all_funds_capital_projects_object_6600_for_td AS capital_projects
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

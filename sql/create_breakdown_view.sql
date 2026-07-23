-- Function-level spending breakdown (MECE categories from TEA function
-- codes), powering GET /district/{id}/breakdown. Run after import.
CREATE OR REPLACE VIEW public.v_spending_breakdown AS
SELECT
    district_number,
    district_name,
    year,
    all_funds_total_operate_expend_by_function                    AS total_operating,
    (COALESCE(all_funds_instruction_transfer_expend_fct11_95, 0)
     + COALESCE(all_funds_instruc_resource_media_service_exp_fct12, 0)
     + COALESCE(all_funds_curriculum_staff_development_exp_fct13, 0)) AS classroom_instruction,
    (COALESCE(all_funds_instruc_leadership_expend_fct21, 0)
     + COALESCE(all_funds_campus_administration_expend_fct23, 0)
     + COALESCE(all_funds_general_administrat_expend_fct41_92, 0))    AS leadership_admin,
    (COALESCE(all_funds_guidance_counseling_services_exp_fct31, 0)
     + COALESCE(all_funds_social_work_services_exp_fct32, 0)
     + COALESCE(all_funds_health_services_exp_fct33, 0))              AS student_support,
    COALESCE(all_funds_transportation_expenditures_fct34, 0)          AS transportation,
    COALESCE(all_funds_food_service_expenditures_fct35, 0)            AS food_service,
    COALESCE(all_funds_extracurricular_expenditures_fct36, 0)         AS extracurricular,
    COALESCE(all_funds_plant_maintenance_opera_expend_fct51, 0)       AS facilities_maintenance,
    (COALESCE(all_funds_security_monitoring_service_expend_fct52, 0)
     + COALESCE(all_funds_data_processing_services_expend_fct53, 0))  AS safety_technology,
    COALESCE(all_funds_community_services_fct61, 0)                   AS community_services,
    COALESCE(all_funds_debt_service_object_6500_for_td, 0)            AS debt_service,
    COALESCE(all_funds_capital_projects_object_6600_for_td, 0)        AS capital_projects
FROM public.texas_school_finance;

GRANT SELECT ON public.v_spending_breakdown TO anon, authenticated;

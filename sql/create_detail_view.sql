-- Two more spending dimensions the summarized data already carries but the
-- dashboard didn't surface: OBJECT (what was bought) and PROGRAM (who it
-- served). Object lines sum exactly to operating spending; program lines are
-- program operating expenditures. Run after import; rebuild is idempotent.
CREATE OR REPLACE VIEW public.v_spending_detail AS
SELECT
    district_number,
    district_name,
    year,
    fall_survey_enrollment AS enrollment,
    -- OBJECT: what the money bought (sums to operating total)
    all_funds_total_payroll_expenditures                       AS obj_payroll,
    all_funds_total_professional_contracted_services_expenditure AS obj_contracted,
    all_funds_total_supplies_materials_expenditures            AS obj_supplies,
    all_funds_total_other_operating_expenditures               AS obj_other,
    all_funds_total_operating_expenditures_by_obj              AS obj_total,
    -- PROGRAM: who the money served
    all_funds_regular_program_expend_11                        AS prog_regular,
    all_funds_students_with_disabilities_pgm_expend_23         AS prog_special_ed,
    all_funds_bilingual_program_exp_25_35                      AS prog_bilingual,
    all_funds_career_technology_pgm_expend_22                  AS prog_career_tech,
    all_funds_gifted_talented_program_expend_21               AS prog_gifted,
    all_funds_state_compensatory_ed_expend_24_26_28_29_30_34  AS prog_compensatory,
    all_funds_athletics_program_expend_91                     AS prog_athletics,
    all_funds_total_program_operating_expenditures            AS prog_total
FROM public.texas_school_finance;

GRANT SELECT ON public.v_spending_detail TO anon, authenticated;

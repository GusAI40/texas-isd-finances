-- Read-only effective-access evidence intended for an explicitly selected target.
WITH roles(role_name) AS (VALUES ('anon'),('authenticated'),('nlp_reader')),
objects(object_name) AS (VALUES ('v_finance_summary'),('v_spending_detail'),
  ('v_spending_breakdown'),('v_district_similarity'),('v_anomaly_flags')),
privileges(privilege_name) AS (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),
  ('TRUNCATE'),('REFERENCES'),('TRIGGER'))
SELECT role_name,object_name,privilege_name,
  has_table_privilege(role_name,'public.'||object_name,privilege_name) AS allowed
FROM roles CROSS JOIN objects CROSS JOIN privileges
ORDER BY role_name,object_name,privilege_name;

SELECT role_name,
  has_schema_privilege(role_name,'public','CREATE') AS can_create,
  has_table_privilege(role_name,'public.texas_school_finance','SELECT') AS can_read_base,
  has_table_privilege(role_name,'public.texas_school_finance','INSERT,UPDATE,DELETE,TRUNCATE') AS can_mutate_base
FROM (VALUES ('anon'),('authenticated'),('nlp_reader')) AS roles(role_name)
ORDER BY role_name;

-- Read-only catalog assertions intended for an explicitly selected target.
SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
WHERE table_schema='public' AND grantee IN ('anon','authenticated','nlp_reader')
ORDER BY grantee, table_name, privilege_type;

-- Least-privilege database role for the natural-language query path.
--
-- Why this exists
-- ---------------
-- `/query` hands a user's plain-English question to an LLM, which writes the
-- SQL itself. Telling the agent about only two views (the `include_tables`
-- argument in src/nlp_engine.py) controls what it *knows about*; it does not
-- control what it is *allowed to run*. A prompt-injected or simply confused
-- agent can emit any statement, and it executes with whatever privileges the
-- connection holds. Until this role exists, that is the owner connection.
--
-- This role closes that gap in the database, where it cannot be talked out of:
-- SELECT on the two public views and nothing else, no schema creation, and
-- every transaction read-only by default so even a well-formed DELETE fails.
--
-- How to apply
-- ------------
--   1. Generate a strong password (e.g. `openssl rand -base64 32`).
--   2. Replace CHANGE_ME below and run this file against the project database
--      (Supabase SQL editor, or the Management API query endpoint).
--   3. Set the Vercel env var NLP_DB_URL to the pooler URL for this role:
--        postgresql://nlp_reader.<PROJECT_REF>:<PASSWORD>@aws-<REGION>.pooler.supabase.com:6543/postgres
--      src/nlp_engine.py prefers NLP_DB_URL and falls back to SUPABASE_DB_URL,
--      so nothing breaks before the variable is set — but the fallback is the
--      privileged connection, so set it.
--   4. Redeploy and confirm /query still answers a sample question.
--
-- Never commit the password. It belongs only in the host's env vars.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nlp_reader') THEN
    CREATE ROLE nlp_reader LOGIN PASSWORD 'CHANGE_ME'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
  END IF;
END
$$;

-- Start from nothing, then grant back only what the agent needs.
REVOKE ALL ON SCHEMA public FROM nlp_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM nlp_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM nlp_reader;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM nlp_reader;
REVOKE ALL ON DATABASE postgres FROM nlp_reader;
GRANT CONNECT ON DATABASE postgres TO nlp_reader;

-- USAGE lets it resolve names in the schema; it does NOT let it create objects.
GRANT USAGE ON SCHEMA public TO nlp_reader;
GRANT SELECT ON public.v_finance_summary TO nlp_reader;
GRANT SELECT ON public.v_anomaly_flags TO nlp_reader;

-- Anything added to `public` later is not readable by this role unless a
-- future migration grants it explicitly. That default is deliberate.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM nlp_reader;

-- Defence in depth, applied server-side so no client setting can undo it:
-- writes fail even if the agent produces a syntactically valid one, and a
-- runaway query cannot hold a pooler slot open.
ALTER ROLE nlp_reader SET default_transaction_read_only = on;
ALTER ROLE nlp_reader SET statement_timeout = '20s';
ALTER ROLE nlp_reader SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE nlp_reader SET search_path = public;

-- Verify (run as the owner):
--   SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
--     FROM pg_roles WHERE rolname = 'nlp_reader';
--   SELECT table_name, privilege_type FROM information_schema.table_privileges
--    WHERE grantee = 'nlp_reader' ORDER BY table_name;
--
-- Then, connected AS nlp_reader, all four of these must fail and the SELECT
-- must succeed:
--   SELECT count(*) FROM public.v_finance_summary;          -- 20587
--   SELECT count(*) FROM public.texas_school_finance;       -- permission denied
--   DELETE FROM public.texas_school_finance;                -- read-only txn
--   CREATE TABLE public.scratch (x int);                    -- permission denied
--   ALTER ROLE nlp_reader SET default_transaction_read_only = off;  -- denied

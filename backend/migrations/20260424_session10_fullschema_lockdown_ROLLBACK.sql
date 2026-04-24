-- =========================================================================
-- ROLLBACK for Session 10 full-schema lockdown
--
-- ⚠️  DO NOT RUN this casually. It re-opens the PostgREST exposure surface.
-- Use only for incident response if the lockdown breaks something we cannot
-- otherwise unbreak.
--
-- Restores: anon + authenticated get full DML on all public tables and
-- EXECUTE on all public functions again; all public-schema RLS is disabled;
-- postgres default privileges re-grant to anon/authenticated.
--
-- Does NOT touch: supabase_admin default ACLs (not in scope for either
-- direction — postgres can't modify them).
-- =========================================================================

BEGIN;

-- Restore grants on existing objects
GRANT ALL ON ALL TABLES    IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO PUBLIC;

-- Disable RLS on every public table
DO $rls_off$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relrowsecurity
  LOOP
    EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', r.relname);
  END LOOP;
END
$rls_off$;

-- Restore postgres default privileges
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON TABLES    TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON FUNCTIONS TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO PUBLIC;

COMMIT;

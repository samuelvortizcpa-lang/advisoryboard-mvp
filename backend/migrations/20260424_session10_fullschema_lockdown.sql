-- =========================================================================
-- Session 10 P0: Full-schema PostgREST/Supabase lockdown
--
-- Scope: every object in schema public that postgres has authority to modify.
--
-- What this does:
--   1. REVOKE ALL on all existing tables from anon, authenticated
--   2. REVOKE ALL on all existing functions from anon, authenticated
--      (succeeds on postgres-owned functions; emits harmless warnings for
--      supabase_admin-owned functions — see residual note below)
--   3. REVOKE ALL on all existing sequences from anon, authenticated
--   4. ENABLE ROW LEVEL SECURITY on every public table (idempotent; tables
--      locked down in Session 9 already have it enabled and are no-ops)
--   5. ALTER DEFAULT PRIVILEGES for role 'postgres' in schema public to
--      prevent future postgres-owned objects from inheriting
--      anon/authenticated grants
--
-- Scope exclusions (and why):
--   - service_role: left as-is. Server-side admin key; if it leaks, blast
--     radius is already total. Revoking breaks Supabase Dashboard.
--   - schema USAGE grant on public for anon/authenticated: left as-is.
--     Table/function-level REVOKE + RLS is the correct layer; revoking
--     schema USAGE cascades oddly into PostgREST/Dashboard introspection.
--   - ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin: NOT ATTEMPTED.
--     postgres is not a member of supabase_admin on Supabase-managed
--     instances, so the statement returns "permission denied to change
--     default privileges". Supabase platform only.
--
-- Known residual exposure (accepted):
--   - ~117 pgvector extension functions (halfvec_*, sparsevec_*, vector_*,
--     l2_distance, cosine_distance, etc.) are owned by supabase_admin and
--     have EXECUTE granted to PUBLIC (and thus anon/authenticated via
--     inheritance). postgres cannot revoke grants on supabase_admin-owned
--     functions, so these remain callable via PostgREST RPC with just
--     the anon key. Assessment: LOW RISK. These are stateless math
--     functions operating on vector types; they do not read tables or
--     touch client data. An attacker calling them gets numeric results
--     on vectors they themselves provide.
--   - Future tables/functions created by supabase_admin in public will
--     still inherit its open default ACL. In practice this only happens
--     during Supabase platform updates / extension installs, not from
--     app migrations.
--
-- PUBLIC pseudo-role treatment:
--   PostgreSQL grants EXECUTE to PUBLIC on every CREATE FUNCTION by
--   default, and anon/authenticated inherit via PUBLIC. This migration
--   also revokes EXECUTE from PUBLIC (step 2b) and strips PUBLIC from
--   the postgres default ACL for future functions (step 5d). Effective
--   on postgres-owned functions only; supabase_admin-owned functions
--   are in the residual above for the same ownership reason.
--
-- Blast radius: zero impact on backend. Backend connects as 'postgres'
-- superuser (BYPASSRLS, bypasses role grants entirely). Frontend has zero
-- direct Supabase-js data queries (verified Session 9 Stretch A.1.5), so
-- REVOKE from anon/authenticated is structurally invisible to the app.
--
-- Pre-Session-9 state: anon + authenticated had full DML (arwdDxtm) on all
-- 54 public tables and EXECUTE on all 120 public functions. Session 9
-- locked down document_chunks + 8 backup tables. This migration locks down
-- the remaining 45 tables + the 2 app-owned functions + the postgres-role
-- default ACLs that were the root cause of the recurrence pathway.
-- =========================================================================

BEGIN;

-- 1. Revoke all privileges on existing public TABLES from anon, authenticated
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;

-- 2. Revoke EXECUTE on all public FUNCTIONS from anon, authenticated.
--    Expect ~117 "no privileges could be revoked" warnings for
--    supabase_admin-owned pgvector functions; these are harmless and
--    are the documented residual above.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

-- 2b. Also revoke EXECUTE from PUBLIC. PostgreSQL's CREATE FUNCTION
--     default grants EXECUTE to PUBLIC, and anon/authenticated inherit
--     via PUBLIC. Without this, the REVOKE above is ineffective.
--     Same ownership barrier applies — only postgres-owned functions
--     are affected; supabase_admin functions hit the warning noise.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

-- 3. Revoke all privileges on public SEQUENCES from anon, authenticated
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;

-- 4. Enable RLS on every public table that doesn't already have it.
--    Idempotent: Session 9's document_chunks family already has relrowsecurity=t
--    and won't appear in the loop.
DO $rls$
DECLARE
  r record;
  n_enabled int := 0;
BEGIN
  FOR r IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND NOT c.relrowsecurity
    ORDER BY c.relname
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.relname);
    n_enabled := n_enabled + 1;
  END LOOP;
  RAISE NOTICE 'Enabled RLS on % tables', n_enabled;
END
$rls$;

-- 5. Fix default privileges for role postgres only. Our app creates tables
--    as postgres, so this closes the recurrence pathway for app code.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- 5d. Also strip EXECUTE from PUBLIC for future postgres-owned functions,
--     so new CREATE FUNCTION calls can't re-open the inheritance pathway.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- 6. Inline verification inside the transaction. RAISE EXCEPTION on any
--    failure so the transaction rolls back and operator sees the error.
--    Verification is scoped to postgres-owned objects — the ones we can
--    actually lock down. supabase_admin-owned residuals are accepted.
DO $verify$
DECLARE
  bad_table_grants int;
  bad_func_grants  int;
  bad_seq_grants   int;
  rls_off          int;
  bad_defacl       int;
BEGIN
  -- 6a. No anon/authenticated grants on public tables
  SELECT COUNT(*) INTO bad_table_grants
  FROM information_schema.role_table_grants
  WHERE table_schema = 'public'
    AND grantee IN ('anon', 'authenticated');
  IF bad_table_grants > 0 THEN
    RAISE EXCEPTION 'LOCKDOWN FAILED: % table-grant rows remain for anon/authenticated', bad_table_grants;
  END IF;

  -- 6b. No EXECUTE grants on postgres-owned public functions for anon/authenticated.
  --     supabase_admin-owned functions (pgvector internals) are out of scope;
  --     see residual note in header.
  SELECT COUNT(*) INTO bad_func_grants
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  JOIN pg_roles    o ON o.oid = p.proowner
  CROSS JOIN (VALUES ('anon'),('authenticated')) AS r(rolname)
  WHERE n.nspname = 'public'
    AND o.rolname = 'postgres'
    AND has_function_privilege(r.rolname, p.oid, 'EXECUTE');
  IF bad_func_grants > 0 THEN
    RAISE EXCEPTION 'LOCKDOWN FAILED: % postgres-owned function EXECUTE grants remain for anon/authenticated', bad_func_grants;
  END IF;

  -- 6c. No sequence grants for anon/authenticated
  SELECT COUNT(*) INTO bad_seq_grants
  FROM information_schema.role_usage_grants
  WHERE object_schema = 'public'
    AND grantee IN ('anon', 'authenticated');
  IF bad_seq_grants > 0 THEN
    RAISE EXCEPTION 'LOCKDOWN FAILED: % sequence grants remain for anon/authenticated', bad_seq_grants;
  END IF;

  -- 6d. Every public table has RLS enabled
  SELECT COUNT(*) INTO rls_off
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind = 'r'
    AND NOT c.relrowsecurity;
  IF rls_off > 0 THEN
    RAISE EXCEPTION 'LOCKDOWN FAILED: % public tables still have RLS disabled', rls_off;
  END IF;

  -- 6e. postgres-owned default ACLs in public no longer grant to anon/authenticated.
  --     supabase_admin-owned default ACLs are out of scope.
  SELECT COUNT(*) INTO bad_defacl
  FROM pg_default_acl d
  JOIN pg_namespace n ON n.oid = d.defaclnamespace
  JOIN pg_roles     o ON o.oid = d.defaclrole
  WHERE n.nspname = 'public'
    AND o.rolname = 'postgres'
    AND (
      array_to_string(defaclacl, ',') LIKE '%anon=%'
      OR array_to_string(defaclacl, ',') LIKE '%authenticated=%'
    );
  IF bad_defacl > 0 THEN
    RAISE EXCEPTION 'LOCKDOWN FAILED: % postgres-owned default-ACL entries still grant to anon/authenticated', bad_defacl;
  END IF;

  RAISE NOTICE 'LOCKDOWN VERIFIED: all 5 checks passed (tables=%, postgres_funcs=%, seqs=%, rls_off=%, postgres_defacl=%)',
               bad_table_grants, bad_func_grants, bad_seq_grants, rls_off, bad_defacl;
END
$verify$;

COMMIT;

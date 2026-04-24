-- Session 9 — April 23, 2026
-- document_chunks family external exposure lockdown
--
-- Context: audit during Session 9 Stretch A found anon and authenticated roles had
-- full DML (SELECT/INSERT/UPDATE/DELETE/TRUNCATE) on public.document_chunks and all
-- 8 public.document_chunks_backup_* tables, with RLS disabled. Supabase PostgREST
-- exposes these grants to any HTTPS client presenting the project anon key.
--
-- Applied against prod via psql during Session 9 Stretch A.2 (second attempt —
-- first attempt via Supabase SQL editor silently did not apply; execution vehicle
-- switched to psql with inline verification).
--
-- No app impact: backend connects as postgres superuser (BYPASSRLS + bypasses
-- grants entirely). Frontend does not use supabase-js.

BEGIN;

REVOKE ALL ON public.document_chunks FROM anon, authenticated;

DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename LIKE 'document_chunks_backup_%'
  LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
  END LOOP;
END $$;

ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename LIKE 'document_chunks_backup_%'
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

COMMIT;

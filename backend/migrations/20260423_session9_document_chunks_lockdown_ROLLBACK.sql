-- ROLLBACK for 20260423_session9_document_chunks_lockdown.sql
-- DO NOT execute unless the lockdown broke prod app functionality.
-- Not expected to be needed: backend uses postgres superuser which bypasses
-- both grants and RLS. Kept here for incident response only.

BEGIN;

GRANT ALL ON public.document_chunks TO anon, authenticated;
ALTER TABLE public.document_chunks DISABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public' AND tablename LIKE 'document_chunks_backup_%'
  LOOP
    EXECUTE format('GRANT ALL ON public.%I TO anon, authenticated', t);
    EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

COMMIT;

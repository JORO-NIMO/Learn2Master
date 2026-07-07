-- ============================================================
-- Learn2Master V8 — Supabase Storage Bucket Setup
-- Run in: Supabase Dashboard → SQL Editor
-- AFTER database_v2_postgres.sql has been executed.
-- ============================================================

-- ── Step 1: Create bucket via Dashboard ──────────────────────
-- Supabase Dashboard → Storage → New Bucket
-- Name:    practical-evidence
-- Public:  NO  (private — requires signed URL or service key)
--
-- Path pattern used by Flask (routes/learning.py):
--   learner_{user_id}/outcome_{outcome_id}/{filename}
-- Example:
--   learner_3/outcome_2/physics_practical_report.pdf

-- ── Step 2: Storage RLS Policies ─────────────────────────────
-- NOTE: The Flask backend uses the service_role key which bypasses
-- all storage RLS automatically. These policies protect direct
-- client-side (browser/JS) access only.
--
-- Because Flask stores files under learner_{integer_id}/... and
-- auth.uid() is a UUID, we use the auth_user_id() helper from
-- database_v2_postgres.sql to resolve the internal user_id.

-- Allow authenticated users to upload their own evidence files
CREATE POLICY "Learners upload own evidence"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'practical-evidence'
    AND (storage.foldername(name))[1] = 'learner_' || auth_user_id()::text
);

-- Allow authenticated users to read their own files
CREATE POLICY "Learners read own evidence"
ON storage.objects FOR SELECT
TO authenticated
USING (
    bucket_id = 'practical-evidence'
    AND (storage.foldername(name))[1] = 'learner_' || auth_user_id()::text
);

-- Allow authenticated users to delete their own files
CREATE POLICY "Learners delete own evidence"
ON storage.objects FOR DELETE
TO authenticated
USING (
    bucket_id = 'practical-evidence'
    AND (storage.foldername(name))[1] = 'learner_' || auth_user_id()::text
);

-- ── Step 3: Verify setup ──────────────────────────────────────
-- SELECT id, name, public FROM storage.buckets WHERE name = 'practical-evidence';
--
-- To test a file upload from Flask, check:
-- SELECT name, bucket_id, created_at FROM storage.objects
-- WHERE bucket_id = 'practical-evidence'
-- ORDER BY created_at DESC LIMIT 5;

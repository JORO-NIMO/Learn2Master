-- ============================================================
-- Learn2Master V8 — Incremental Migration: content ownership
-- Run this ONCE in Supabase Dashboard → SQL Editor
-- Adds created_by to content tables so teachers only see/edit
-- their own content. Existing rows default to NULL (no owner).
-- ============================================================

-- Learning Outcomes
ALTER TABLE learning_outcomes
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(user_id);

-- Lessons
ALTER TABLE lessons
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(user_id);

-- Questions
ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(user_id);

-- Adaptive Notes
ALTER TABLE adaptive_notes
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(user_id);

-- Adaptive Videos
ALTER TABLE adaptive_videos
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(user_id);

-- Worked Examples
ALTER TABLE worked_examples
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(user_id);

-- Index for efficient ownership filtering
CREATE INDEX IF NOT EXISTS idx_lo_created_by        ON learning_outcomes(created_by);
CREATE INDEX IF NOT EXISTS idx_lessons_created_by   ON lessons(created_by);
CREATE INDEX IF NOT EXISTS idx_questions_created_by ON questions(created_by);
CREATE INDEX IF NOT EXISTS idx_notes_created_by     ON adaptive_notes(created_by);
CREATE INDEX IF NOT EXISTS idx_videos_created_by    ON adaptive_videos(created_by);
CREATE INDEX IF NOT EXISTS idx_examples_created_by  ON worked_examples(created_by);

-- ============================================================
-- BKT parameter defaults in system_settings
-- Run this ONCE (ON CONFLICT DO NOTHING = safe to re-run)
-- ============================================================
INSERT INTO system_settings (setting_key, setting_value, setting_description)
VALUES
  ('bkt_p_learn', '0.12',
   'BKT: probability a learner masters a concept on each new attempt'),
  ('bkt_p_slip',  '0.10',
   'BKT: probability a learner who knows a concept answers incorrectly'),
  ('bkt_p_guess', '0.20',
   'BKT: probability a learner who does not know guesses correctly')
ON CONFLICT (setting_key) DO NOTHING;

-- ============================================================
-- Learn2Master V8 — PostgreSQL / Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor
-- ============================================================

-- Drop tables in reverse FK order (safe re-run)
DROP TABLE IF EXISTS audit_logs             CASCADE;
DROP TABLE IF EXISTS system_settings        CASCADE;
DROP TABLE IF EXISTS bkt_mastery            CASCADE;
DROP TABLE IF EXISTS practical_evidence     CASCADE;
DROP TABLE IF EXISTS worked_examples        CASCADE;
DROP TABLE IF EXISTS activity_logs          CASCADE;
DROP TABLE IF EXISTS recommendations        CASCADE;
DROP TABLE IF EXISTS concept_mastery        CASCADE;
DROP TABLE IF EXISTS mastery_records        CASCADE;
DROP TABLE IF EXISTS attempt_answers        CASCADE;
DROP TABLE IF EXISTS assessment_attempts    CASCADE;
DROP TABLE IF EXISTS question_options       CASCADE;
DROP TABLE IF EXISTS questions              CASCADE;
DROP TABLE IF EXISTS assessments            CASCADE;
DROP TABLE IF EXISTS adaptive_videos        CASCADE;
DROP TABLE IF EXISTS adaptive_notes         CASCADE;
DROP TABLE IF EXISTS learning_activities    CASCADE;
DROP TABLE IF EXISTS lessons                CASCADE;
DROP TABLE IF EXISTS courses                CASCADE;
DROP TABLE IF EXISTS learning_outcomes      CASCADE;
DROP TABLE IF EXISTS competencies           CASCADE;
DROP TABLE IF EXISTS subjects               CASCADE;
DROP TABLE IF EXISTS enrollments            CASCADE;
DROP TABLE IF EXISTS classes                CASCADE;
DROP TABLE IF EXISTS learner_profiles       CASCADE;
DROP TABLE IF EXISTS learning_reflections   CASCADE;
DROP TABLE IF EXISTS teacher_interventions  CASCADE;
DROP TABLE IF EXISTS evidence_portfolio     CASCADE;
DROP TABLE IF EXISTS ai_explanations        CASCADE;
DROP TABLE IF EXISTS offline_sync_queue     CASCADE;
DROP TABLE IF EXISTS users                  CASCADE;
DROP TABLE IF EXISTS schools                CASCADE;
DROP TABLE IF EXISTS roles                  CASCADE;

-- ── Identity & Access ────────────────────────────────────────

CREATE TABLE roles (
    role_id   SERIAL PRIMARY KEY,
    role_name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE schools (
    school_id   SERIAL PRIMARY KEY,
    school_name VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    full_name     VARCHAR(255) NOT NULL,
    username      VARCHAR(100) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE,
    password_hash TEXT NOT NULL,
    role_id       INTEGER NOT NULL REFERENCES roles(role_id),
    school_id     INTEGER REFERENCES schools(school_id),
    supabase_uid  UUID UNIQUE,          -- Links to auth.users.id (Option B / future Supabase Auth)
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE classes (
    class_id    SERIAL PRIMARY KEY,
    class_name  VARCHAR(100) NOT NULL,
    school_id   INTEGER NOT NULL REFERENCES schools(school_id)
);

CREATE TABLE enrollments (
    enrollment_id SERIAL PRIMARY KEY,
    learner_id    INTEGER NOT NULL REFERENCES users(user_id),
    class_id      INTEGER NOT NULL REFERENCES classes(class_id),
    enrolled_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (learner_id, class_id)
);

-- ── Curriculum ───────────────────────────────────────────────

CREATE TABLE subjects (
    subject_id   SERIAL PRIMARY KEY,
    subject_name VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE competencies (
    competency_id          SERIAL PRIMARY KEY,
    subject_id             INTEGER NOT NULL REFERENCES subjects(subject_id),
    competency_code        VARCHAR(50) NOT NULL,
    competency_name        VARCHAR(255) NOT NULL,
    competency_description TEXT,
    UNIQUE (subject_id, competency_code)
);

CREATE TABLE learning_outcomes (
    outcome_id          SERIAL PRIMARY KEY,
    competency_id       INTEGER NOT NULL REFERENCES competencies(competency_id),
    outcome_code        VARCHAR(50) NOT NULL,
    outcome_name        VARCHAR(255) NOT NULL,
    outcome_description TEXT,
    mastery_threshold   INTEGER DEFAULT 80,
    sequence_order      INTEGER NOT NULL,
    UNIQUE (competency_id, outcome_code)
);

CREATE TABLE courses (
    course_id          SERIAL PRIMARY KEY,
    subject_id         INTEGER NOT NULL REFERENCES subjects(subject_id),
    course_title       VARCHAR(255) NOT NULL,
    course_description TEXT,
    difficulty_level   VARCHAR(50)
);

CREATE TABLE lessons (
    lesson_id          SERIAL PRIMARY KEY,
    course_id          INTEGER NOT NULL REFERENCES courses(course_id),
    outcome_id         INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    lesson_title       VARCHAR(255) NOT NULL,
    lesson_content     TEXT,
    video_url          TEXT,
    estimated_minutes  INTEGER,
    sequence_order     INTEGER NOT NULL
);

CREATE TABLE learning_activities (
    activity_id          SERIAL PRIMARY KEY,
    outcome_id           INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    activity_title       VARCHAR(255) NOT NULL,
    activity_description TEXT NOT NULL,
    activity_type        VARCHAR(50) DEFAULT 'Practice'
);

CREATE TABLE adaptive_notes (
    note_id     SERIAL PRIMARY KEY,
    outcome_id  INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    concept_tag VARCHAR(100) NOT NULL,
    note_title  VARCHAR(255) NOT NULL,
    note_body   TEXT NOT NULL,
    priority    INTEGER DEFAULT 1
);

CREATE TABLE adaptive_videos (
    video_id          SERIAL PRIMARY KEY,
    outcome_id        INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    concept_tag       VARCHAR(100) NOT NULL,
    video_title       VARCHAR(255) NOT NULL,
    video_url         TEXT NOT NULL,
    video_description TEXT
);

CREATE TABLE worked_examples (
    example_id            SERIAL PRIMARY KEY,
    outcome_id            INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    concept_tag           VARCHAR(100) NOT NULL,
    example_title         VARCHAR(255) NOT NULL,
    example_body          TEXT NOT NULL,
    step_by_step_solution TEXT
);

-- ── Assessment Engine ────────────────────────────────────────

CREATE TABLE assessments (
    assessment_id    SERIAL PRIMARY KEY,
    lesson_id        INTEGER NOT NULL REFERENCES lessons(lesson_id),
    assessment_title VARCHAR(255) NOT NULL,
    assessment_type  VARCHAR(20) NOT NULL CHECK (assessment_type IN ('pretest','practice','posttest')),
    total_marks      INTEGER DEFAULT 0
);

CREATE TABLE questions (
    question_id      SERIAL PRIMARY KEY,
    assessment_id    INTEGER NOT NULL REFERENCES assessments(assessment_id),
    question_text    TEXT NOT NULL,
    concept_tag      VARCHAR(100) NOT NULL,
    difficulty_level VARCHAR(50) DEFAULT 'standard',
    question_type    VARCHAR(50) DEFAULT 'multiple_choice',
    marks            INTEGER DEFAULT 1
);

CREATE TABLE question_options (
    option_id    SERIAL PRIMARY KEY,
    question_id  INTEGER NOT NULL REFERENCES questions(question_id),
    option_text  TEXT NOT NULL,
    is_correct   BOOLEAN DEFAULT FALSE
);

CREATE TABLE assessment_attempts (
    attempt_id    SERIAL PRIMARY KEY,
    learner_id    INTEGER NOT NULL REFERENCES users(user_id),
    assessment_id INTEGER NOT NULL REFERENCES assessments(assessment_id),
    score         REAL DEFAULT 0,
    weak_concepts TEXT,
    attempted_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE attempt_answers (
    answer_id          SERIAL PRIMARY KEY,
    attempt_id         INTEGER NOT NULL REFERENCES assessment_attempts(attempt_id),
    question_id        INTEGER NOT NULL REFERENCES questions(question_id),
    selected_option_id INTEGER REFERENCES question_options(option_id),
    is_correct         BOOLEAN DEFAULT FALSE
);

-- ── Mastery & AI Tracking ────────────────────────────────────

CREATE TABLE concept_mastery (
    concept_mastery_id     SERIAL PRIMARY KEY,
    learner_id             INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id             INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    concept_tag            VARCHAR(100) NOT NULL,
    latest_score           REAL DEFAULT 0,
    latest_assessment_type VARCHAR(20),
    attempt_count          INTEGER DEFAULT 0,
    concept_status         VARCHAR(50) DEFAULT 'Not Practiced',
    updated_at             TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (learner_id, outcome_id, concept_tag)
);

CREATE TABLE mastery_records (
    mastery_id        SERIAL PRIMARY KEY,
    learner_id        INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id        INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    pretest_score     REAL DEFAULT 0,
    practice_score    REAL DEFAULT 0,
    posttest_score    REAL DEFAULT 0,
    improvement_score REAL DEFAULT 0,
    mastery_score     REAL DEFAULT 0,
    mastery_level     VARCHAR(50) NOT NULL,
    mastery_status    VARCHAR(50) NOT NULL,
    is_unlocked       BOOLEAN DEFAULT FALSE,
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (learner_id, outcome_id)
);

CREATE TABLE recommendations (
    recommendation_id   SERIAL PRIMARY KEY,
    learner_id          INTEGER NOT NULL REFERENCES users(user_id),
    lesson_id           INTEGER NOT NULL REFERENCES lessons(lesson_id),
    outcome_id          INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    recommendation_reason TEXT NOT NULL,
    recommendation_type VARCHAR(100),
    teacher_status      VARCHAR(50) DEFAULT 'Pending Review',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE bkt_mastery (
    bkt_id              SERIAL PRIMARY KEY,
    learner_id          INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id          INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    concept_tag         VARCHAR(100) NOT NULL,
    probability_mastery REAL DEFAULT 0.20,
    observations        INTEGER DEFAULT 0,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (learner_id, outcome_id, concept_tag)
);

-- ── Evidence & Collaboration ─────────────────────────────────

CREATE TABLE learner_profiles (
    profile_id        SERIAL PRIMARY KEY,
    learner_id        INTEGER NOT NULL UNIQUE REFERENCES users(user_id),
    class_level       VARCHAR(50) DEFAULT 'Senior One',
    learning_style    VARCHAR(100) DEFAULT 'Adaptive / Mixed',
    learning_pace     VARCHAR(100) DEFAULT 'Not yet classified',
    preferred_support TEXT DEFAULT 'Notes, video and guided practice',
    ai_profile_summary TEXT DEFAULT 'Learner profile will update from assessment evidence.',
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE learning_reflections (
    reflection_id    SERIAL PRIMARY KEY,
    learner_id       INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id       INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    reflection_text  TEXT NOT NULL,
    confidence_level INTEGER DEFAULT 3,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE teacher_interventions (
    intervention_id   SERIAL PRIMARY KEY,
    teacher_id        INTEGER NOT NULL REFERENCES users(user_id),
    learner_id        INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id        INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    intervention_type VARCHAR(100) NOT NULL,
    intervention_note TEXT NOT NULL,
    status            VARCHAR(50) DEFAULT 'Assigned',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE evidence_portfolio (
    evidence_id     SERIAL PRIMARY KEY,
    learner_id      INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id      INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    evidence_type   VARCHAR(100) NOT NULL,
    evidence_status VARCHAR(50) NOT NULL,
    evidence_note   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE practical_evidence (
    practical_id      SERIAL PRIMARY KEY,
    learner_id        INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id        INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    evidence_title    VARCHAR(255) NOT NULL,
    evidence_description TEXT,
    file_path         TEXT,           -- Supabase Storage URL
    teacher_status    VARCHAR(50) DEFAULT 'Pending Review',
    teacher_comment   TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at       TIMESTAMPTZ
);

CREATE TABLE ai_explanations (
    explanation_id   SERIAL PRIMARY KEY,
    learner_id       INTEGER NOT NULL REFERENCES users(user_id),
    outcome_id       INTEGER NOT NULL REFERENCES learning_outcomes(outcome_id),
    decision_type    VARCHAR(100) NOT NULL,
    evidence_used    TEXT,
    explanation_text TEXT NOT NULL,
    confidence_score REAL DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── System & Logging ─────────────────────────────────────────

CREATE TABLE activity_logs (
    log_id               SERIAL PRIMARY KEY,
    learner_id           INTEGER NOT NULL REFERENCES users(user_id),
    activity_type        VARCHAR(100) NOT NULL,
    activity_description TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE offline_sync_queue (
    sync_id     SERIAL PRIMARY KEY,
    learner_id  INTEGER REFERENCES users(user_id),
    event_type  VARCHAR(100) NOT NULL,
    payload     TEXT,
    sync_status VARCHAR(50) DEFAULT 'Pending',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    synced_at   TIMESTAMPTZ
);

CREATE TABLE system_settings (
    setting_id          SERIAL PRIMARY KEY,
    setting_key         VARCHAR(100) UNIQUE NOT NULL,
    setting_value       TEXT NOT NULL,
    setting_description TEXT
);

CREATE TABLE audit_logs (
    audit_id    SERIAL PRIMARY KEY,
    actor_id    INTEGER REFERENCES users(user_id),
    action      VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id   VARCHAR(100),
    details     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Performance Indexes ──────────────────────────────────────

CREATE INDEX idx_mastery_learner       ON mastery_records(learner_id);
CREATE INDEX idx_mastery_outcome       ON mastery_records(outcome_id);
CREATE INDEX idx_attempts_learner      ON assessment_attempts(learner_id);
CREATE INDEX idx_concept_mastery_l_o   ON concept_mastery(learner_id, outcome_id);
CREATE INDEX idx_bkt_learner_outcome   ON bkt_mastery(learner_id, outcome_id);
CREATE INDEX idx_activity_logs_learner ON activity_logs(learner_id);
CREATE INDEX idx_recommendations_learner ON recommendations(learner_id);
CREATE INDEX idx_users_username        ON users(username);
CREATE INDEX idx_users_email           ON users(email);
CREATE INDEX idx_ai_explanations_learner ON ai_explanations(learner_id);
CREATE INDEX idx_practical_evidence_learner ON practical_evidence(learner_id);

-- ── Auto-update updated_at trigger ──────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mastery_records_updated
    BEFORE UPDATE ON mastery_records
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_concept_mastery_updated
    BEFORE UPDATE ON concept_mastery
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_bkt_mastery_updated
    BEFORE UPDATE ON bkt_mastery
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_learner_profiles_updated
    BEFORE UPDATE ON learner_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Row Level Security (RLS) ─────────────────────────────────
-- NOTE ON ARCHITECTURE:
-- The Flask backend connects with the service_role key — this BYPASSES RLS
-- automatically. No Flask route is affected by these policies.
--
-- RLS policies below protect the Supabase PostgREST/JS client API only,
-- preventing direct database access from the browser without Flask.
--
-- For Option A (current): Flask sessions handle auth; RLS is a safety net.
-- For Option B (future): Enable Supabase Auth, populate users.supabase_uid,
-- and the helper function below links auth.uid() → user_id automatically.

ALTER TABLE users                ENABLE ROW LEVEL SECURITY;
ALTER TABLE mastery_records      ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessment_attempts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE attempt_answers      ENABLE ROW LEVEL SECURITY;
ALTER TABLE concept_mastery      ENABLE ROW LEVEL SECURITY;
ALTER TABLE bkt_mastery          ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_reflections ENABLE ROW LEVEL SECURITY;
ALTER TABLE practical_evidence   ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE teacher_interventions ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE offline_sync_queue   ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_explanations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_portfolio   ENABLE ROW LEVEL SECURITY;
ALTER TABLE learner_profiles     ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_settings      ENABLE ROW LEVEL SECURITY;

-- Curriculum tables: read-only public access (authenticated users only)
ALTER TABLE roles              ENABLE ROW LEVEL SECURITY;
ALTER TABLE subjects           ENABLE ROW LEVEL SECURITY;
ALTER TABLE competencies       ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_outcomes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE courses            ENABLE ROW LEVEL SECURITY;
ALTER TABLE lessons            ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated read roles"             ON roles              FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read subjects"          ON subjects           FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read competencies"      ON competencies       FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read learning_outcomes" ON learning_outcomes  FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read courses"           ON courses            FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read lessons"           ON lessons            FOR SELECT TO authenticated USING (true);

-- ── RLS Helper: resolve auth.uid() → internal user_id ────────
-- Returns the internal integer user_id for the currently authenticated
-- Supabase user (matched via supabase_uid UUID column on users).
-- Returns NULL if not authenticated or not linked (Option A mode).
CREATE OR REPLACE FUNCTION auth_user_id()
RETURNS INTEGER AS $$
    SELECT user_id FROM users WHERE supabase_uid = auth.uid()
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

-- ── Data table RLS policies ───────────────────────────────────
-- All learner-scoped policies use auth_user_id() for correct type matching.
-- In Option A (Flask sessions), auth_user_id() returns NULL and these
-- policies deny all direct API access — which is correct and intended.

CREATE POLICY "Users read own row" ON users FOR SELECT TO authenticated
    USING (user_id = auth_user_id());

CREATE POLICY "Learner mastery own rows" ON mastery_records FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner attempts own rows" ON assessment_attempts FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner concept mastery own rows" ON concept_mastery FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner bkt own rows" ON bkt_mastery FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner reflections own rows" ON learning_reflections FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner practical evidence own rows" ON practical_evidence FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner recommendations own rows" ON recommendations FOR SELECT TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner activity logs own rows" ON activity_logs FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner sync queue own rows" ON offline_sync_queue FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner ai explanations own rows" ON ai_explanations FOR SELECT TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner evidence portfolio own rows" ON evidence_portfolio FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

CREATE POLICY "Learner profile own row" ON learner_profiles FOR ALL TO authenticated
    USING (learner_id = auth_user_id());

-- ── Seed Data ────────────────────────────────────────────────

INSERT INTO roles (role_name) VALUES ('student'),('teacher'),('admin')
    ON CONFLICT DO NOTHING;

INSERT INTO schools (school_name) VALUES ('Kigezi High School'),('Kigata High School')
    ON CONFLICT DO NOTHING;

INSERT INTO subjects (subject_name) VALUES ('ICT'),('Physics')
    ON CONFLICT DO NOTHING;

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS system_settings;
DROP TABLE IF EXISTS bkt_mastery;
DROP TABLE IF EXISTS practical_evidence;
DROP TABLE IF EXISTS worked_examples;
DROP TABLE IF EXISTS activity_logs;
DROP TABLE IF EXISTS recommendations;
DROP TABLE IF EXISTS concept_mastery;
DROP TABLE IF EXISTS mastery_records;
DROP TABLE IF EXISTS attempt_answers;
DROP TABLE IF EXISTS assessment_attempts;
DROP TABLE IF EXISTS question_options;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS assessments;
DROP TABLE IF EXISTS adaptive_videos;
DROP TABLE IF EXISTS adaptive_notes;
DROP TABLE IF EXISTS learning_activities;
DROP TABLE IF EXISTS lessons;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS learning_outcomes;
DROP TABLE IF EXISTS competencies;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS classes;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS schools;
DROP TABLE IF EXISTS roles;

CREATE TABLE roles (
    role_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT UNIQUE NOT NULL
);

CREATE TABLE schools (
    school_id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_name TEXT UNIQUE NOT NULL
);

CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    school_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(role_id),
    FOREIGN KEY (school_id) REFERENCES schools(school_id)
);

CREATE TABLE classes (
    class_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    school_id INTEGER NOT NULL,
    FOREIGN KEY (school_id) REFERENCES schools(school_id)
);

CREATE TABLE enrollments (
    enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    enrolled_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (class_id) REFERENCES classes(class_id),
    UNIQUE (learner_id, class_id)
);

CREATE TABLE subjects (
    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT UNIQUE NOT NULL
);

CREATE TABLE competencies (
    competency_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    competency_code TEXT NOT NULL,
    competency_name TEXT NOT NULL,
    competency_description TEXT,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    UNIQUE (subject_id, competency_code)
);

CREATE TABLE learning_outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    competency_id INTEGER NOT NULL,
    outcome_code TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    outcome_description TEXT,
    mastery_threshold INTEGER DEFAULT 80,
    sequence_order INTEGER NOT NULL,
    FOREIGN KEY (competency_id) REFERENCES competencies(competency_id),
    UNIQUE (competency_id, outcome_code)
);

CREATE TABLE courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    course_title TEXT NOT NULL,
    course_description TEXT,
    difficulty_level TEXT,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

CREATE TABLE lessons (
    lesson_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    lesson_title TEXT NOT NULL,
    lesson_content TEXT,
    video_url TEXT,
    estimated_minutes INTEGER,
    sequence_order INTEGER NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE learning_activities (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id INTEGER NOT NULL,
    activity_title TEXT NOT NULL,
    activity_description TEXT NOT NULL,
    activity_type TEXT DEFAULT 'Practice',
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE adaptive_notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id INTEGER NOT NULL,
    concept_tag TEXT NOT NULL,
    note_title TEXT NOT NULL,
    note_body TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE adaptive_videos (
    video_id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id INTEGER NOT NULL,
    concept_tag TEXT NOT NULL,
    video_title TEXT NOT NULL,
    video_url TEXT NOT NULL,
    video_description TEXT,
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE assessments (
    assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL,
    assessment_title TEXT NOT NULL,
    assessment_type TEXT NOT NULL CHECK (assessment_type IN ('pretest','practice','posttest')),
    total_marks INTEGER DEFAULT 0,
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id)
);

CREATE TABLE questions (
    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    concept_tag TEXT NOT NULL,
    difficulty_level TEXT DEFAULT 'standard',
    question_type TEXT DEFAULT 'multiple_choice',
    marks INTEGER DEFAULT 1,
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id)
);

CREATE TABLE question_options (
    option_id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    is_correct INTEGER DEFAULT 0,
    FOREIGN KEY (question_id) REFERENCES questions(question_id)
);

CREATE TABLE assessment_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    assessment_id INTEGER NOT NULL,
    score REAL DEFAULT 0,
    weak_concepts TEXT,
    attempted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id)
);

CREATE TABLE attempt_answers (
    answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    selected_option_id INTEGER,
    is_correct INTEGER DEFAULT 0,
    FOREIGN KEY (attempt_id) REFERENCES assessment_attempts(attempt_id),
    FOREIGN KEY (question_id) REFERENCES questions(question_id),
    FOREIGN KEY (selected_option_id) REFERENCES question_options(option_id)
);

CREATE TABLE concept_mastery (
    concept_mastery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    concept_tag TEXT NOT NULL,
    latest_score REAL DEFAULT 0,
    latest_assessment_type TEXT,
    attempt_count INTEGER DEFAULT 0,
    concept_status TEXT DEFAULT 'Not Practiced',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id),
    UNIQUE (learner_id, outcome_id, concept_tag)
);

CREATE TABLE mastery_records (
    mastery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    pretest_score REAL DEFAULT 0,
    practice_score REAL DEFAULT 0,
    posttest_score REAL DEFAULT 0,
    improvement_score REAL DEFAULT 0,
    mastery_score REAL DEFAULT 0,
    mastery_level TEXT NOT NULL,
    mastery_status TEXT NOT NULL,
    is_unlocked INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id),
    UNIQUE (learner_id, outcome_id)
);

CREATE TABLE recommendations (
    recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    lesson_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    recommendation_reason TEXT NOT NULL,
    recommendation_type TEXT,
    teacher_status TEXT DEFAULT 'Pending Review',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE activity_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    activity_type TEXT NOT NULL,
    activity_description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id)
);



-- Research-grade alignment tables
CREATE TABLE IF NOT EXISTS learner_profiles (
    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL UNIQUE,
    class_level TEXT DEFAULT 'Senior One',
    learning_style TEXT DEFAULT 'Adaptive / Mixed',
    learning_pace TEXT DEFAULT 'Not yet classified',
    preferred_support TEXT DEFAULT 'Notes, video and guided practice',
    ai_profile_summary TEXT DEFAULT 'Learner profile will update from assessment evidence.',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS learning_reflections (
    reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    reflection_text TEXT NOT NULL,
    confidence_level INTEGER DEFAULT 3,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS teacher_interventions (
    intervention_id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    intervention_type TEXT NOT NULL,
    intervention_note TEXT NOT NULL,
    status TEXT DEFAULT 'Assigned',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(user_id),
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS evidence_portfolio (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    evidence_note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS ai_explanations (
    explanation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    decision_type TEXT NOT NULL,
    evidence_used TEXT,
    explanation_text TEXT NOT NULL,
    confidence_score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS offline_sync_queue (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER,
    event_type TEXT NOT NULL,
    payload TEXT,
    sync_status TEXT DEFAULT 'Pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    synced_at TEXT,
    FOREIGN KEY (learner_id) REFERENCES users(user_id)
);



-- V8 dissertation-final proposal alignment tables
CREATE TABLE IF NOT EXISTS worked_examples (
    example_id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id INTEGER NOT NULL,
    concept_tag TEXT NOT NULL,
    example_title TEXT NOT NULL,
    example_body TEXT NOT NULL,
    step_by_step_solution TEXT,
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS practical_evidence (
    practical_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    evidence_title TEXT NOT NULL,
    evidence_description TEXT,
    file_path TEXT,
    teacher_status TEXT DEFAULT 'Pending Review',
    teacher_comment TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS bkt_mastery (
    bkt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    outcome_id INTEGER NOT NULL,
    concept_tag TEXT NOT NULL,
    probability_mastery REAL DEFAULT 0.20,
    observations INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES users(user_id),
    FOREIGN KEY (outcome_id) REFERENCES learning_outcomes(outcome_id),
    UNIQUE (learner_id, outcome_id, concept_tag)
);

CREATE TABLE IF NOT EXISTS system_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT UNIQUE NOT NULL,
    setting_value TEXT NOT NULL,
    setting_description TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (actor_id) REFERENCES users(user_id)
);

INSERT INTO roles (role_name) VALUES ('student'), ('teacher'), ('admin');
INSERT INTO schools (school_name) VALUES ('Kigezi High School'), ('Kigata High School');
INSERT INTO subjects (subject_name) VALUES ('ICT'), ('Physics');

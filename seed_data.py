import os
import sqlite3
import logging
from werkzeug.security import generate_password_hash

try:
    import psycopg2
except ImportError:
    psycopg2 = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    if DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")):
        if not psycopg2:
            raise ImportError("psycopg2 is required for PostgreSQL support")
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        return conn, conn.cursor(), "%s"
    elif DATABASE_URL and DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, conn.cursor(), "?"
    else:
        conn = sqlite3.connect("learn2master.db")
        conn.row_factory = sqlite3.Row
        return conn, conn.cursor(), "?"

conn, cur, p = get_connection()

def get_id(query, params=()):
    q = query.replace("?", p)
    cur.execute(q, params)
    row = cur.fetchone()
    return row[0] if row else None

def execute(query, params=()):
    q = query.replace("?", p)
    cur.execute(q, params)

# --- Start Seeding ---
logger.info("Starting seed process...")

# Roles
roles = [
    ('super_admin', 'Super Administrator'),
    ('school_admin', 'School Administrator'),
    ('teacher', 'Teacher'),
    ('learner', 'Learner'),
]

for name, display in roles:
    execute("INSERT INTO roles (role_name, display_name) SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM roles WHERE role_name=?)", (name, display, name))

# School
execute("INSERT INTO schools (school_name) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM schools WHERE school_name=?)", ('Kigezi High School', 'Kigezi High School'))
school_id = get_id("SELECT school_id FROM schools WHERE school_name='Kigezi High School'")

# Users
pwd_hash = generate_password_hash('12345')
users = [
    ('superadmin', 'Super Admin', 'super_admin'),
    ('admin', 'School Admin', 'school_admin'),
    ('teacher', 'Main Teacher', 'teacher'),
    ('elijah', 'Elijah Learner', 'learner'),
]

for username, full_name, role_name in users:
    role_id = get_id("SELECT role_id FROM roles WHERE role_name=?", (role_name,))
    execute("""
        INSERT INTO users (username, full_name, password_hash, role_id, school_id, account_status, must_change_password)
        SELECT ?, ?, ?, ?, ?, 'Active', 0
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE username=?)
    """, (username, full_name, pwd_hash, role_id, school_id, username))

conn.commit()

# Subjects
execute("INSERT INTO subjects (subject_name) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM subjects WHERE subject_name=?)", ('ICT', 'ICT'))
ict_id = get_id("SELECT subject_id FROM subjects WHERE subject_name='ICT'")

execute("INSERT INTO subjects (subject_name) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM subjects WHERE subject_name=?)", ('Physics', 'Physics'))
physics_id = get_id("SELECT subject_id FROM subjects WHERE subject_name='Physics'")

# Topics
execute("INSERT INTO topics (subject_id, topic_title) VALUES (?, ?)", (ict_id, 'Introduction to ICT'))
topic_id = get_id("SELECT topic_id FROM topics WHERE topic_title='Introduction to ICT'")

# Competencies
execute("INSERT INTO competencies (subject_id, topic_id, competency_code, competency_name) VALUES (?, ?, ?, ?)",
        (ict_id, topic_id, 'ICT-C1', 'Basic ICT Concepts'))
comp_id = get_id("SELECT competency_id FROM competencies WHERE competency_code='ICT-C1'")

# Learning Outcomes
outcomes = [
    (comp_id, topic_id, 'ICT-LO1', 'Identify ICT Components', 1),
    (comp_id, topic_id, 'ICT-LO2', 'Explain ICT Functions', 2),
]

for c_id, t_id, code, name, seq in outcomes:
    execute("""
        INSERT INTO learning_outcomes (competency_id, topic_id, outcome_code, outcome_name, sequence_order)
        VALUES (?, ?, ?, ?, ?)
    """, (c_id, t_id, code, name, seq))
    o_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=?", (code,))

    # Lesson
    execute("INSERT INTO lessons (course_id, outcome_id, lesson_title, sequence_order) VALUES (?, ?, ?, ?)",
            (1, o_id, f"Lesson on {name}", seq))
    l_id = get_id("SELECT lesson_id FROM lessons WHERE outcome_id=?", (o_id,))

    # Assessments
    for atype in ['pretest', 'practice', 'posttest']:
        execute("INSERT INTO assessments (lesson_id, assessment_title, assessment_type) VALUES (?, ?, ?)",
                (l_id, f"{name} {atype}", atype))
        aid = get_id("SELECT assessment_id FROM assessments WHERE lesson_id=? AND assessment_type=?", (l_id, atype))

        # Question
        execute("""
            INSERT INTO questions (assessment_id, question_text, concept_tag, correct_answer)
            VALUES (?, ?, ?, ?)
        """, (aid, f"Question for {code} {atype}", "General", "1"))
        qid = get_id("SELECT question_id FROM questions WHERE assessment_id=?", (aid,))

        # Option
        execute("INSERT INTO question_options (question_id, option_text, is_correct) VALUES (?, ?, 1)",
                (qid, "Correct Option"))

# System Settings
settings = [
    ('ai_adaptivity_level', 'balanced', 'AI & Personalization Settings', 'select'),
    ('at_risk_threshold', '60', 'Notifications & Interventions', 'number'),
]

for key, val, cat, stype in settings:
    execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_category, setting_type)
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE setting_key=?)
    """, (key, val, cat, stype, key))

conn.commit()
logger.info("Seed process completed successfully!")
conn.close()

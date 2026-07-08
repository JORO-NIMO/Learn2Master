"""
tests/conftest.py — Shared pytest fixtures for Learn2Master property-based tests.

Uses a live PostgreSQL connection (same DATABASE_URL as the application).
Each test that writes data runs inside a transaction that is rolled back
after the test, keeping the database clean.

Session setup creates the minimum prerequisite rows (roles, subject,
competency, course, assessment) that all tests depend on.
"""

import os
import pytest
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")


# ── Raw connection factory ────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_conn():
    """Open a single psycopg2 connection for the entire test session."""
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    yield conn
    conn.close()


@pytest.fixture
def db(db_conn):
    """
    Per-test transactional fixture.

    Starts a SAVEPOINT before each test and rolls back to it afterwards,
    so no test data leaks between tests.
    """
    db_conn.execute("SAVEPOINT test_savepoint")
    yield db_conn
    db_conn.execute("ROLLBACK TO SAVEPOINT test_savepoint")


# ── Prerequisite data helpers ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def prereq_ids(db_conn):
    """
    Create (or resolve) the minimum curriculum and user rows needed by all tests.
    These are created once per session inside a nested savepoint so they survive
    individual test rollbacks.

    Returns a dict with:
        subject_id, competency_id, course_id, assessment_id,
        teacher_user_id, student_user_id, admin_user_id
    """
    cur = db_conn.cursor()

    # ── Roles (must already exist from schema seed) ───────────────────────────
    cur.execute("SELECT role_id FROM roles WHERE role_name = 'teacher'")
    teacher_role_id = cur.fetchone()["role_id"]
    cur.execute("SELECT role_id FROM roles WHERE role_name = 'student'")
    student_role_id = cur.fetchone()["role_id"]
    cur.execute("SELECT role_id FROM roles WHERE role_name = 'admin'")
    admin_role_id = cur.fetchone()["role_id"]

    # ── Subject ───────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO subjects (subject_name)
        VALUES ('Test Subject PBT')
        ON CONFLICT (subject_name) DO UPDATE SET subject_name = EXCLUDED.subject_name
        RETURNING subject_id
    """)
    subject_id = cur.fetchone()["subject_id"]

    # ── Competency ────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO competencies (subject_id, competency_code, competency_name)
        VALUES (%s, 'PBT-COMP-1', 'PBT Test Competency')
        ON CONFLICT (subject_id, competency_code)
        DO UPDATE SET competency_name = EXCLUDED.competency_name
        RETURNING competency_id
    """, (subject_id,))
    competency_id = cur.fetchone()["competency_id"]

    # ── Course ────────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO courses (subject_id, course_title)
        VALUES (%s, 'PBT Test Course')
        ON CONFLICT DO NOTHING
        RETURNING course_id
    """, (subject_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "SELECT course_id FROM courses WHERE course_title = 'PBT Test Course'"
        )
        row = cur.fetchone()
    course_id = row["course_id"]

    # ── Learning Outcome (baseline) ───────────────────────────────────────────
    cur.execute("""
        INSERT INTO learning_outcomes
            (competency_id, outcome_code, outcome_name, outcome_description,
             mastery_threshold, sequence_order)
        VALUES (%s, 'PBT-LO-BASE', 'PBT Base Outcome', 'Base outcome for PBT fixtures', 80, 1)
        ON CONFLICT (competency_id, outcome_code)
        DO UPDATE SET outcome_name = EXCLUDED.outcome_name
        RETURNING outcome_id
    """, (competency_id,))
    base_outcome_id = cur.fetchone()["outcome_id"]

    # ── Lesson ────────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO lessons (course_id, outcome_id, lesson_title, sequence_order)
        VALUES (%s, %s, 'PBT Base Lesson', 1)
        ON CONFLICT DO NOTHING
        RETURNING lesson_id
    """, (course_id, base_outcome_id))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "SELECT lesson_id FROM lessons WHERE lesson_title = 'PBT Base Lesson'"
        )
        row = cur.fetchone()
    lesson_id = row["lesson_id"]

    # ── Assessment ────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO assessments (lesson_id, assessment_title, assessment_type)
        VALUES (%s, 'PBT Base Assessment', 'practice')
        ON CONFLICT DO NOTHING
        RETURNING assessment_id
    """, (lesson_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "SELECT assessment_id FROM assessments WHERE assessment_title = 'PBT Base Assessment'"
        )
        row = cur.fetchone()
    assessment_id = row["assessment_id"]

    # ── Teacher user ──────────────────────────────────────────────────────────
    from werkzeug.security import generate_password_hash
    cur.execute("""
        INSERT INTO users (full_name, username, email, password_hash, role_id)
        VALUES ('PBT Teacher', 'pbt_teacher_fixture', 'pbt_teacher@test.invalid',
                %s, %s)
        ON CONFLICT (username) DO UPDATE SET full_name = EXCLUDED.full_name
        RETURNING user_id
    """, (generate_password_hash("pbt_pass"), teacher_role_id))
    teacher_user_id = cur.fetchone()["user_id"]

    # ── Student user ──────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO users (full_name, username, email, password_hash, role_id)
        VALUES ('PBT Student', 'pbt_student_fixture', 'pbt_student@test.invalid',
                %s, %s)
        ON CONFLICT (username) DO UPDATE SET full_name = EXCLUDED.full_name
        RETURNING user_id
    """, (generate_password_hash("pbt_pass"), student_role_id))
    student_user_id = cur.fetchone()["user_id"]

    # ── Admin user ────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO users (full_name, username, email, password_hash, role_id)
        VALUES ('PBT Admin', 'pbt_admin_fixture', 'pbt_admin@test.invalid',
                %s, %s)
        ON CONFLICT (username) DO UPDATE SET full_name = EXCLUDED.full_name
        RETURNING user_id
    """, (generate_password_hash("pbt_pass"), admin_role_id))
    admin_user_id = cur.fetchone()["user_id"]

    db_conn.commit()
    cur.close()

    return {
        "subject_id":      subject_id,
        "competency_id":   competency_id,
        "course_id":       course_id,
        "base_outcome_id": base_outcome_id,
        "lesson_id":       lesson_id,
        "assessment_id":   assessment_id,
        "teacher_user_id": teacher_user_id,
        "student_user_id": student_user_id,
        "admin_user_id":   admin_user_id,
    }


# ── Flask test client ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def flask_app():
    """Return the Flask application in test mode."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from app import app as _app
    _app.config["TESTING"] = True
    _app.config["WTF_CSRF_ENABLED"] = False   # disable CSRF for test client
    _app.config["SECRET_KEY"] = "test-secret-key-pbt"
    return _app


@pytest.fixture
def client(flask_app):
    """Return a Flask test client."""
    with flask_app.test_client() as c:
        yield c


def login_as(client, username="pbt_teacher_fixture", password="pbt_pass"):
    """POST to /login and return the response."""
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=True)

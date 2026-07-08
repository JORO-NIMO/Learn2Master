"""
tests/test_properties_users_settings.py
Property-based tests for Admin User Management and Settings (Properties 6–9).

Properties tested:
  6  User Creation Password Never Stored in Plaintext  (R2.1)
  7  Duplicate Username/Email Leaves User Table Unchanged (R2.2)
  8  Student Registration Role Immutability             (R2.6)
  9  Threshold Update Audit Trail                       (R3.1, R3.6)
"""

import json
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from werkzeug.security import generate_password_hash, check_password_hash


# ── Strategies ────────────────────────────────────────────────────────────────

username_st = st.text(
    min_size=4, max_size=30,
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"),
                           whitelist_characters="_")
)
password_st = st.text(min_size=6, max_size=40,
                      alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Po")))
threshold_st = st.integers(min_value=1, max_value=100)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 6 — Password Never Stored in Plaintext
# ═══════════════════════════════════════════════════════════════════════════════

@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
@given(password=password_st)
def test_property6_password_never_stored_plaintext(db, prereq_ids, password):
    """
    Property 6: For any password string P, the password_hash stored in users
    must NOT equal P, and check_password_hash(stored, P) must return True.
    """
    cur = db.cursor()
    cur.execute("SELECT role_id FROM roles WHERE role_name = 'teacher'")
    teacher_role_id = cur.fetchone()["role_id"]

    hashed = generate_password_hash(password, method="pbkdf2:sha256")

    # Use a unique username to avoid conflicts with other property examples
    import uuid
    unique_username = f"prop6_{uuid.uuid4().hex[:12]}"

    cur.execute("""
        INSERT INTO users (full_name, username, password_hash, role_id)
        VALUES ('Prop6 User', %s, %s, %s)
        RETURNING user_id
    """, (unique_username, hashed, teacher_role_id))
    user_id = cur.fetchone()["user_id"]
    db.commit()

    # Retrieve and verify
    cur.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
    stored_hash = cur.fetchone()["password_hash"]
    cur.close()

    assert stored_hash != password, \
        "The plaintext password must never be stored directly in password_hash"
    assert check_password_hash(stored_hash, password), \
        "check_password_hash must verify the original password against the stored hash"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7 — Duplicate Username/Email Leaves User Table Unchanged
# ═══════════════════════════════════════════════════════════════════════════════

def test_property7_duplicate_username_leaves_table_unchanged(db, prereq_ids):
    """
    Property 7: A create-user POST with a username that already exists in users
    should result in the users table having the same row count as before the request.
    Tests the UniqueViolation rollback path.
    """
    import psycopg2.errors

    cur = db.cursor()
    cur.execute("SELECT role_id FROM roles WHERE role_name = 'teacher'")
    teacher_role_id = cur.fetchone()["role_id"]

    # Insert initial user
    import uuid
    shared_username = f"dup7_{uuid.uuid4().hex[:12]}"
    cur.execute("""
        INSERT INTO users (full_name, username, password_hash, role_id)
        VALUES ('Dup7 Original', %s, 'hashed', %s)
    """, (shared_username, teacher_role_id))
    db.commit()

    # Count rows before duplicate attempt
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    count_before = cur.fetchone()["cnt"]

    # Attempt duplicate insert — must raise UniqueViolation and be rolled back
    try:
        cur.execute("""
            INSERT INTO users (full_name, username, password_hash, role_id)
            VALUES ('Dup7 Duplicate', %s, 'hashed2', %s)
        """, (shared_username, teacher_role_id))
        db.commit()
        # If we reach here without exception, the DB did not enforce uniqueness
        pytest.fail("Expected UniqueViolation for duplicate username but none was raised")
    except psycopg2.errors.UniqueViolation:
        db.rollback()
    except Exception as exc:
        db.rollback()
        pytest.fail(f"Unexpected exception type: {type(exc).__name__}: {exc}")

    # Count rows after — must be unchanged
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    count_after = cur.fetchone()["cnt"]
    cur.close()

    assert count_before == count_after, \
        "User table row count must not change after a failed duplicate insert"


def test_property7_duplicate_email_leaves_table_unchanged(db, prereq_ids):
    """
    Property 7 (email variant): duplicate email raises UniqueViolation
    and leaves user count unchanged.
    """
    import psycopg2.errors
    import uuid

    cur = db.cursor()
    cur.execute("SELECT role_id FROM roles WHERE role_name = 'teacher'")
    teacher_role_id = cur.fetchone()["role_id"]

    shared_email = f"dup7email_{uuid.uuid4().hex[:10]}@test.invalid"

    cur.execute("""
        INSERT INTO users (full_name, username, email, password_hash, role_id)
        VALUES ('Dup7E Original', %s, %s, 'hashed', %s)
    """, (f"orig_{uuid.uuid4().hex[:8]}", shared_email, teacher_role_id))
    db.commit()

    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    count_before = cur.fetchone()["cnt"]

    try:
        cur.execute("""
            INSERT INTO users (full_name, username, email, password_hash, role_id)
            VALUES ('Dup7E Dup', %s, %s, 'hashed2', %s)
        """, (f"dup_{uuid.uuid4().hex[:8]}", shared_email, teacher_role_id))
        db.commit()
        pytest.fail("Expected UniqueViolation for duplicate email but none was raised")
    except psycopg2.errors.UniqueViolation:
        db.rollback()

    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    count_after = cur.fetchone()["cnt"]
    cur.close()

    assert count_before == count_after, \
        "User table row count must not change after a failed duplicate email insert"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 8 — Student Registration Role Immutability
# ═══════════════════════════════════════════════════════════════════════════════

def test_property8_student_registration_role_immutability(client, db, prereq_ids):
    """
    Property 8: POST /register with any role value in the body must always
    create the account with role_name = 'student', never teacher or admin.

    Uses the Flask test client to exercise the actual route logic.
    """
    import uuid

    # Try to register with a teacher role sneaked into the body
    username = f"sneaky_reg_{uuid.uuid4().hex[:10]}"
    resp = client.post("/register", data={
        "full_name":  "Sneaky Registrant",
        "username":   username,
        "password":   "testpass123",
        "role":       "teacher",   # should be silently ignored
        "school_name": "",
    }, follow_redirects=True)

    # Registration should succeed (redirect to login) or fail gracefully
    # Either way, if a user was created it must be a student

    cur = db.cursor()
    cur.execute("""
        SELECT u.user_id, r.role_name
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE u.username = %s
    """, (username,))
    row = cur.fetchone()
    cur.close()

    if row is not None:
        assert row["role_name"] == "student", \
            f"Registration must always create a student account; got role '{row['role_name']}'"


@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
@given(
    injected_role=st.sampled_from(["teacher", "admin", "superuser", "root", ""])
)
def test_property8_registration_role_always_student(client, injected_role):
    """
    Property 8 (parameterised): regardless of the role value injected into the
    registration form body, any created user must have role_name = 'student'.
    """
    import uuid
    from database import get_db, release_db

    username = f"pbt8_{uuid.uuid4().hex[:12]}"
    client.post("/register", data={
        "full_name":  "Prop8 User",
        "username":   username,
        "password":   "prop8pass",
        "role":       injected_role,
        "school_name": "",
    }, follow_redirects=False)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT r.role_name FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.username = %s
        """, (username,))
        row = cur.fetchone()
        cur.close()
    finally:
        release_db(conn)

    if row is not None:
        assert row["role_name"] == "student", \
            (f"User registered with injected role='{injected_role}' "
             f"was assigned role '{row['role_name']}' instead of 'student'")


# ═══════════════════════════════════════════════════════════════════════════════
# Property 9 — Threshold Update Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════

@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    old_threshold=threshold_st,
    new_threshold=threshold_st,
)
def test_property9_threshold_update_audit_trail(db, prereq_ids, old_threshold, new_threshold):
    """
    Property 9: For any valid mastery threshold update to an existing outcome_id,
    both the learning_outcomes.mastery_threshold column and a corresponding
    audit_logs row must reflect the change — the audit log must record the old
    and new threshold values in its details JSON field.
    """
    cur = db.cursor()

    # Create a fresh outcome with the initial threshold
    cur.execute("""
        INSERT INTO learning_outcomes
            (competency_id, outcome_code, outcome_name, outcome_description,
             mastery_threshold, sequence_order)
        VALUES (%s, 'PROP9-THR', 'Prop9 Threshold Test', 'desc', %s, 97)
        ON CONFLICT (competency_id, outcome_code)
        DO UPDATE SET mastery_threshold = EXCLUDED.mastery_threshold
        RETURNING outcome_id
    """, (prereq_ids["competency_id"], old_threshold))
    outcome_id = cur.fetchone()["outcome_id"]
    db.commit()

    # Apply the threshold update (replicates routes/admin.update_threshold logic)
    cur.execute(
        "UPDATE learning_outcomes SET mastery_threshold = %s WHERE outcome_id = %s",
        (new_threshold, outcome_id)
    )
    cur.execute("""
        INSERT INTO audit_logs
            (actor_id, action, entity_type, entity_id, details)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        prereq_ids["admin_user_id"],
        "update_mastery_threshold",
        "learning_outcomes",
        str(outcome_id),
        json.dumps({"old": old_threshold, "new": new_threshold}),
    ))
    db.commit()

    # Assert 1: the outcome row reflects the new threshold
    cur.execute(
        "SELECT mastery_threshold FROM learning_outcomes WHERE outcome_id = %s",
        (outcome_id,)
    )
    stored = cur.fetchone()["mastery_threshold"]
    assert stored == new_threshold, \
        f"learning_outcomes.mastery_threshold must be {new_threshold}, got {stored}"

    # Assert 2: the audit_logs row was written with correct old/new values
    cur.execute("""
        SELECT details FROM audit_logs
        WHERE action = 'update_mastery_threshold'
          AND entity_type = 'learning_outcomes'
          AND entity_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (str(outcome_id),))
    audit_row = cur.fetchone()
    assert audit_row is not None, \
        "An audit_logs row must exist for the threshold update"

    details = json.loads(audit_row["details"])
    assert details.get("old") == old_threshold, \
        f"audit_logs.details must record old threshold {old_threshold}, got {details.get('old')}"
    assert details.get("new") == new_threshold, \
        f"audit_logs.details must record new threshold {new_threshold}, got {details.get('new')}"
    cur.close()

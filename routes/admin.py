"""routes/admin.py — Admin dashboard routes (Supabase/PostgreSQL edition)."""
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, session
import psycopg2
import psycopg2.errors
from werkzeug.security import generate_password_hash
from routes.guards import role_required
from database import get_db, release_db

admin_bp = Blueprint("admin", __name__)


def _admin_summary(cur):
    """Build the admin summary dict using an open cursor."""

    def one(sql, params=()):
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return 0
        val = list(row.values())[0]
        return val if val is not None else 0

    cur.execute("""
        SELECT roles.role_name, COUNT(users.user_id) AS total
        FROM roles
        LEFT JOIN users ON users.role_id = roles.role_id
        GROUP BY roles.role_name
        ORDER BY roles.role_name
    """)
    role_counts = cur.fetchall()

    return {
        "users":           one("SELECT COUNT(*) FROM users"),
        "students":        one("SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='student'"),
        "teachers":        one("SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='teacher'"),
        "admins":          one("SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='admin'"),
        "schools":         one("SELECT COUNT(*) FROM schools"),
        "subjects":        one("SELECT COUNT(*) FROM subjects"),
        "competencies":    one("SELECT COUNT(*) FROM competencies"),
        "outcomes":        one("SELECT COUNT(*) FROM learning_outcomes"),
        "courses":         one("SELECT COUNT(*) FROM courses"),
        "questions":       one("SELECT COUNT(*) FROM questions"),
        "attempts":        one("SELECT COUNT(*) FROM assessment_attempts"),
        "recommendations": one("SELECT COUNT(*) FROM recommendations"),
        "role_counts":     role_counts,
    }


@admin_bp.route("/admin")
@role_required("admin")
def admin_dashboard():
    conn = get_db()
    try:
        cur = conn.cursor()
        summary = _admin_summary(cur)
        cur.execute("""
            SELECT users.full_name, users.username, users.email,
                   roles.role_name, schools.school_name, users.created_at
            FROM users
            JOIN roles ON users.role_id = roles.role_id
            LEFT JOIN schools ON users.school_id = schools.school_id
            ORDER BY users.created_at DESC
            LIMIT 8
        """)
        recent_users = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/dashboard.html", summary=summary, recent_users=recent_users)


@admin_bp.route("/admin/users")
@role_required("admin")
def users():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT users.user_id, users.full_name, users.username, users.email,
                   roles.role_name, schools.school_name, users.created_at
            FROM users
            JOIN roles ON users.role_id = roles.role_id
            LEFT JOIN schools ON users.school_id = schools.school_id
            ORDER BY roles.role_name, users.full_name
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/users.html", users=rows)


ALLOWED_ROLES = {"teacher", "admin"}


@admin_bp.route("/admin/users/create", methods=["GET", "POST"])
@role_required("admin")
def create_user():
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT school_id, school_name FROM schools ORDER BY school_name")
            schools = cur.fetchall()
            cur.close()
        finally:
            release_db(conn)
        return render_template("admin/create_user.html", schools=schools)

    # POST — provision a new teacher or admin account
    full_name = request.form.get("full_name", "").strip()
    username  = request.form.get("username", "").strip()
    email     = request.form.get("email", "").strip() or None
    password  = request.form.get("password", "")
    role      = request.form.get("role", "").strip()
    school_id = request.form.get("school_id") or None

    if role not in ALLOWED_ROLES:
        abort(400)

    # Convert empty school_id string to None (optional field)
    if school_id is not None:
        try:
            school_id = int(school_id)
        except (ValueError, TypeError):
            school_id = None

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM roles WHERE role_name = %s", (role,))
        role_row = cur.fetchone()
        if not role_row:
            abort(400)

        cur.execute("""
            INSERT INTO users (full_name, username, email, password_hash, role_id, school_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            full_name,
            username,
            email,
            generate_password_hash(password, method="pbkdf2:sha256"),
            role_row["role_id"],
            school_id,
        ))
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash("Username or email already exists.", "danger")
        return redirect(url_for("admin.create_user"))
    finally:
        release_db(conn)

    flash(f"{role.title()} account created successfully.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/admin/schools")
@role_required("admin")
def schools():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT schools.school_id, schools.school_name,
                   COUNT(DISTINCT classes.class_id)  AS classes,
                   COUNT(DISTINCT users.user_id)     AS users
            FROM schools
            LEFT JOIN classes ON classes.school_id = schools.school_id
            LEFT JOIN users   ON users.school_id   = schools.school_id
            GROUP BY schools.school_id, schools.school_name
            ORDER BY schools.school_name
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/schools.html", schools=rows)


@admin_bp.route("/admin/curriculum")
@role_required("admin")
def curriculum():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT subjects.subject_name, courses.course_title,
                   competencies.competency_code, competencies.competency_name,
                   learning_outcomes.outcome_code, learning_outcomes.outcome_name,
                   learning_outcomes.mastery_threshold, learning_outcomes.sequence_order
            FROM learning_outcomes
            JOIN competencies ON learning_outcomes.competency_id = competencies.competency_id
            JOIN subjects ON competencies.subject_id = subjects.subject_id
            LEFT JOIN lessons ON lessons.outcome_id = learning_outcomes.outcome_id
            LEFT JOIN courses ON lessons.course_id = courses.course_id
            ORDER BY subjects.subject_name, learning_outcomes.sequence_order
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/curriculum.html", rows=rows)


@admin_bp.route("/admin/competencies")
@role_required("admin")
def competencies():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT subjects.subject_name, competencies.competency_code,
                   competencies.competency_name, competencies.competency_description,
                   COUNT(learning_outcomes.outcome_id) AS outcomes
            FROM competencies
            JOIN subjects ON competencies.subject_id = subjects.subject_id
            LEFT JOIN learning_outcomes ON learning_outcomes.competency_id = competencies.competency_id
            GROUP BY competencies.competency_id, subjects.subject_name,
                     competencies.competency_code, competencies.competency_name,
                     competencies.competency_description
            ORDER BY subjects.subject_name, competencies.competency_code
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/competencies.html", rows=rows)


@admin_bp.route("/admin/questions")
@role_required("admin")
def questions():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT subjects.subject_name, assessments.assessment_type, assessments.assessment_title,
                   questions.question_text, questions.concept_tag,
                   questions.difficulty_level, questions.marks
            FROM questions
            JOIN assessments ON questions.assessment_id = assessments.assessment_id
            JOIN lessons ON assessments.lesson_id = lessons.lesson_id
            JOIN courses ON lessons.course_id = courses.course_id
            JOIN subjects ON courses.subject_id = subjects.subject_id
            ORDER BY subjects.subject_name, assessments.assessment_type,
                     questions.concept_tag, questions.question_id
            LIMIT 200
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/questions.html", rows=rows)


@admin_bp.route("/admin/settings")
@role_required("admin")
def settings():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT lo.outcome_id, lo.outcome_code, lo.outcome_name,
                   lo.mastery_threshold, lo.sequence_order,
                   s.subject_name
            FROM learning_outcomes lo
            JOIN competencies c ON lo.competency_id = c.competency_id
            JOIN subjects s ON c.subject_id = s.subject_id
            ORDER BY s.subject_name, lo.sequence_order
        """)
        thresholds = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/settings.html", thresholds=thresholds)


@admin_bp.route("/admin/settings/threshold/<int:outcome_id>", methods=["POST"])
@role_required("admin")
def update_threshold(outcome_id):
    raw = request.form.get("mastery_threshold", "")
    try:
        new_threshold = int(raw)
        if not (1 <= new_threshold <= 100):
            raise ValueError
    except (ValueError, TypeError):
        flash("Threshold must be an integer between 1 and 100.", "danger")
        return redirect(url_for("admin.settings"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT mastery_threshold FROM learning_outcomes WHERE outcome_id = %s",
            (outcome_id,)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            abort(404)

        old_threshold = row["mastery_threshold"]
        cur.execute(
            "UPDATE learning_outcomes SET mastery_threshold = %s WHERE outcome_id = %s",
            (new_threshold, outcome_id)
        )
        cur.execute("""
            INSERT INTO audit_logs
                (actor_id, action, entity_type, entity_id, details)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            session["user_id"],
            "update_mastery_threshold",
            "learning_outcomes",
            str(outcome_id),
            json.dumps({"old": old_threshold, "new": new_threshold})
        ))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash(f"Threshold updated to {new_threshold}%.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/admin/logs")
@role_required("admin")
def logs():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT activity_logs.*, users.full_name
            FROM activity_logs
            JOIN users ON activity_logs.learner_id = users.user_id
            ORDER BY activity_logs.created_at DESC
            LIMIT 100
        """)
        activity = cur.fetchall()
        cur.execute("SELECT * FROM offline_sync_queue ORDER BY created_at DESC LIMIT 50")
        sync = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/logs.html", activity=activity, sync=sync)


@admin_bp.route("/admin/reports")
@role_required("admin")
def reports():
    conn = get_db()
    try:
        cur = conn.cursor()
        summary = _admin_summary(cur)
        cur.execute("""
            SELECT subjects.subject_name,
                   COUNT(mastery_records.mastery_id) AS records,
                   SUM(CASE WHEN mastery_records.mastery_status='Mastered' THEN 1 ELSE 0 END) AS mastered,
                   ROUND(AVG(mastery_records.mastery_score)::numeric, 1) AS avg_mastery
            FROM subjects
            LEFT JOIN competencies     ON competencies.subject_id       = subjects.subject_id
            LEFT JOIN learning_outcomes ON learning_outcomes.competency_id = competencies.competency_id
            LEFT JOIN mastery_records  ON mastery_records.outcome_id    = learning_outcomes.outcome_id
            GROUP BY subjects.subject_id, subjects.subject_name
            ORDER BY subjects.subject_name
        """)
        mastery = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("admin/reports.html", summary=summary, mastery=mastery)

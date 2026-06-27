from flask import Blueprint, render_template
from routes.guards import role_required
from database import get_db

admin_bp = Blueprint("admin", __name__)


def admin_summary(conn):
    def one(sql, params=()):
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    role_counts = conn.execute("""
        SELECT roles.role_name, COUNT(users.user_id) AS total
        FROM roles
        LEFT JOIN users ON users.role_id = roles.role_id
        GROUP BY roles.role_name
        ORDER BY roles.role_name
    """).fetchall()

    return {
        "users": one("SELECT COUNT(*) FROM users"),
        "students": one("SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='student'"),
        "teachers": one("SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='teacher'"),
        "admins": one("SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='admin'"),
        "schools": one("SELECT COUNT(*) FROM schools"),
        "subjects": one("SELECT COUNT(*) FROM subjects"),
        "competencies": one("SELECT COUNT(*) FROM competencies"),
        "outcomes": one("SELECT COUNT(*) FROM learning_outcomes"),
        "courses": one("SELECT COUNT(*) FROM courses"),
        "questions": one("SELECT COUNT(*) FROM questions"),
        "attempts": one("SELECT COUNT(*) FROM assessment_attempts"),
        "recommendations": one("SELECT COUNT(*) FROM recommendations"),
        "role_counts": role_counts,
    }


@admin_bp.route("/admin")
@role_required("admin")
def admin_dashboard():
    conn = get_db()
    summary = admin_summary(conn)
    recent_users = conn.execute("""
        SELECT users.full_name, users.username, users.email, roles.role_name, schools.school_name, users.created_at
        FROM users
        JOIN roles ON users.role_id = roles.role_id
        LEFT JOIN schools ON users.school_id = schools.school_id
        ORDER BY users.created_at DESC
        LIMIT 8
    """).fetchall()
    conn.close()
    return render_template("admin/dashboard.html", summary=summary, recent_users=recent_users)


@admin_bp.route("/admin/users")
@role_required("admin")
def users():
    conn = get_db()
    rows = conn.execute("""
        SELECT users.user_id, users.full_name, users.username, users.email, roles.role_name, schools.school_name, users.created_at
        FROM users
        JOIN roles ON users.role_id = roles.role_id
        LEFT JOIN schools ON users.school_id = schools.school_id
        ORDER BY roles.role_name, users.full_name
    """).fetchall()
    conn.close()
    return render_template("admin/users.html", users=rows)


@admin_bp.route("/admin/schools")
@role_required("admin")
def schools():
    conn = get_db()
    rows = conn.execute("""
        SELECT schools.school_id, schools.school_name,
               COUNT(DISTINCT classes.class_id) AS classes,
               COUNT(DISTINCT users.user_id) AS users
        FROM schools
        LEFT JOIN classes ON classes.school_id = schools.school_id
        LEFT JOIN users ON users.school_id = schools.school_id
        GROUP BY schools.school_id
        ORDER BY schools.school_name
    """).fetchall()
    conn.close()
    return render_template("admin/schools.html", schools=rows)


@admin_bp.route("/admin/curriculum")
@role_required("admin")
def curriculum():
    conn = get_db()
    rows = conn.execute("""
        SELECT subjects.subject_name, courses.course_title, competencies.competency_code,
               competencies.competency_name, learning_outcomes.outcome_code,
               learning_outcomes.outcome_name, learning_outcomes.mastery_threshold,
               learning_outcomes.sequence_order
        FROM learning_outcomes
        JOIN competencies ON learning_outcomes.competency_id = competencies.competency_id
        JOIN subjects ON competencies.subject_id = subjects.subject_id
        LEFT JOIN lessons ON lessons.outcome_id = learning_outcomes.outcome_id
        LEFT JOIN courses ON lessons.course_id = courses.course_id
        ORDER BY subjects.subject_name, learning_outcomes.sequence_order
    """).fetchall()
    conn.close()
    return render_template("admin/curriculum.html", rows=rows)


@admin_bp.route("/admin/competencies")
@role_required("admin")
def competencies():
    conn = get_db()
    rows = conn.execute("""
        SELECT subjects.subject_name, competencies.competency_code, competencies.competency_name,
               competencies.competency_description, COUNT(learning_outcomes.outcome_id) AS outcomes
        FROM competencies
        JOIN subjects ON competencies.subject_id = subjects.subject_id
        LEFT JOIN learning_outcomes ON learning_outcomes.competency_id = competencies.competency_id
        GROUP BY competencies.competency_id
        ORDER BY subjects.subject_name, competencies.competency_code
    """).fetchall()
    conn.close()
    return render_template("admin/competencies.html", rows=rows)


@admin_bp.route("/admin/questions")
@role_required("admin")
def questions():
    conn = get_db()
    rows = conn.execute("""
        SELECT subjects.subject_name, assessments.assessment_type, assessments.assessment_title,
               questions.question_text, questions.concept_tag, questions.difficulty_level, questions.marks
        FROM questions
        JOIN assessments ON questions.assessment_id = assessments.assessment_id
        JOIN lessons ON assessments.lesson_id = lessons.lesson_id
        JOIN courses ON lessons.course_id = courses.course_id
        JOIN subjects ON courses.subject_id = subjects.subject_id
        ORDER BY subjects.subject_name, assessments.assessment_type, questions.concept_tag, questions.question_id
        LIMIT 200
    """).fetchall()
    conn.close()
    return render_template("admin/questions.html", rows=rows)


@admin_bp.route("/admin/settings")
@role_required("admin")
def settings():
    conn = get_db()
    thresholds = conn.execute("""
        SELECT subjects.subject_name, learning_outcomes.outcome_code, learning_outcomes.outcome_name,
               learning_outcomes.mastery_threshold
        FROM learning_outcomes
        JOIN competencies ON learning_outcomes.competency_id=competencies.competency_id
        JOIN subjects ON competencies.subject_id=subjects.subject_id
        ORDER BY subjects.subject_name, learning_outcomes.sequence_order
    """).fetchall()
    conn.close()
    return render_template("admin/settings.html", thresholds=thresholds)


@admin_bp.route("/admin/logs")
@role_required("admin")
def logs():
    conn = get_db()
    activity = conn.execute("""
        SELECT activity_logs.*, users.full_name
        FROM activity_logs
        JOIN users ON activity_logs.learner_id = users.user_id
        ORDER BY activity_logs.created_at DESC
        LIMIT 100
    """).fetchall()
    sync = conn.execute("SELECT * FROM offline_sync_queue ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return render_template("admin/logs.html", activity=activity, sync=sync)


@admin_bp.route("/admin/reports")
@role_required("admin")
def reports():
    conn = get_db()
    summary = admin_summary(conn)
    mastery = conn.execute("""
        SELECT subjects.subject_name, COUNT(mastery_records.mastery_id) AS records,
               SUM(CASE WHEN mastery_records.mastery_status='Mastered' THEN 1 ELSE 0 END) AS mastered,
               ROUND(AVG(mastery_records.mastery_score), 1) AS avg_mastery
        FROM subjects
        LEFT JOIN competencies ON competencies.subject_id = subjects.subject_id
        LEFT JOIN learning_outcomes ON learning_outcomes.competency_id = competencies.competency_id
        LEFT JOIN mastery_records ON mastery_records.outcome_id = learning_outcomes.outcome_id
        GROUP BY subjects.subject_id
        ORDER BY subjects.subject_name
    """).fetchall()
    conn.close()
    return render_template("admin/reports.html", summary=summary, mastery=mastery)

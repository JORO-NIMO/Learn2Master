"""routes/teacher.py — Teacher dashboard routes (Supabase/PostgreSQL edition)."""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from routes.guards import role_required
from database import get_db, release_db
from services.analytics_engine import teacher_overview, recent_ai_recommendations

teacher_bp = Blueprint("teacher", __name__)


def _get_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    """
    Generate a Supabase Storage signed URL for a private file.
    Returns the signed URL, or the raw storage_path if Supabase is not configured.
    """
    if not storage_path or not storage_path.startswith("supabase://"):
        return storage_path or ""

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        return storage_path

    from supabase import create_client
    # Path format: supabase://practical-evidence/learner_3/outcome_2/file.pdf
    path_part = storage_path.replace("supabase://practical-evidence/", "")
    sb = create_client(supabase_url, supabase_key)
    result = sb.storage.from_("practical-evidence").create_signed_url(path_part, expires_in)
    return result.get("signedURL") or storage_path


def _learner_rows(cur):
    cur.execute("""
        SELECT learner.user_id, learner.full_name, learner.username, learner.email,
               COALESCE(lp.class_level,    'Senior One')        AS class_level,
               COALESCE(lp.learning_pace,  'Not classified')    AS learning_pace,
               COALESCE(lp.learning_style, 'Adaptive / Mixed')  AS learning_style,
               COUNT(mr.mastery_id)                             AS mastery_records,
               SUM(CASE WHEN mr.mastery_status='Mastered' THEN 1 ELSE 0 END) AS mastered_records,
               ROUND(AVG(COALESCE(mr.mastery_score, 0))::numeric, 1) AS avg_mastery
        FROM users learner
        JOIN roles r ON learner.role_id = r.role_id
        LEFT JOIN learner_profiles lp ON lp.learner_id = learner.user_id
        LEFT JOIN mastery_records mr  ON mr.learner_id  = learner.user_id
        WHERE r.role_name = 'student'
        GROUP BY learner.user_id, learner.full_name, learner.username, learner.email,
                 lp.class_level, lp.learning_pace, lp.learning_style
        ORDER BY learner.full_name
    """)
    return cur.fetchall()


@teacher_bp.route("/teacher")
@role_required("teacher", "admin")
def teacher_dashboard():
    conn = get_db()
    try:
        overview        = teacher_overview(conn)
        recommendations = recent_ai_recommendations(conn)
        cur = conn.cursor()

        cur.execute("""
            SELECT ti.*, learner.full_name AS learner_name, lo.outcome_name
            FROM teacher_interventions ti
            JOIN users learner ON ti.learner_id = learner.user_id
            JOIN learning_outcomes lo ON ti.outcome_id = lo.outcome_id
            ORDER BY ti.created_at DESC LIMIT 8
        """)
        interventions = cur.fetchall()

        cur.execute("""
            SELECT cm.concept_tag,
                   ROUND(AVG(cm.latest_score)::numeric, 1) AS avg_score,
                   COUNT(*) AS evidence
            FROM concept_mastery cm
            GROUP BY cm.concept_tag
            ORDER BY avg_score ASC
            LIMIT 6
        """)
        weak = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "teacher/dashboard.html",
        overview=overview,
        recommendations=recommendations,
        interventions=interventions,
        weak=weak,
    )


@teacher_bp.route("/teacher/learners")
@role_required("teacher", "admin")
def learners():
    conn = get_db()
    try:
        cur = conn.cursor()
        rows = _learner_rows(cur)
        cur.close()
    finally:
        release_db(conn)
    return render_template("teacher/learners.html", learners=rows)


@teacher_bp.route("/teacher/mastery-monitor")
@role_required("teacher", "admin")
def mastery_monitor():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT learner.full_name, subjects.subject_name,
                   lo.outcome_code, lo.outcome_name,
                   COALESCE(mr.pretest_score,  0)            AS pretest_score,
                   COALESCE(mr.practice_score, 0)            AS practice_score,
                   COALESCE(mr.posttest_score, 0)            AS posttest_score,
                   COALESCE(mr.mastery_score,  0)            AS mastery_score,
                   COALESCE(mr.mastery_level, 'Beginning')   AS mastery_level,
                   COALESCE(mr.mastery_status,'Not Started') AS mastery_status
            FROM learning_outcomes lo
            JOIN competencies c ON lo.competency_id = c.competency_id
            JOIN subjects ON c.subject_id = subjects.subject_id
            CROSS JOIN users learner
            JOIN roles r ON learner.role_id = r.role_id AND r.role_name = 'student'
            LEFT JOIN mastery_records mr
                ON mr.outcome_id = lo.outcome_id AND mr.learner_id = learner.user_id
            ORDER BY learner.full_name, subjects.subject_name, lo.sequence_order
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("teacher/mastery_monitor.html", rows=rows)


@teacher_bp.route("/teacher/ai-insights")
@role_required("teacher", "admin")
def ai_insights():
    conn = get_db()
    try:
        recommendations = recent_ai_recommendations(conn, limit=30)
        cur = conn.cursor()
        cur.execute("""
            SELECT ai.*, learner.full_name, lo.outcome_name
            FROM ai_explanations ai
            JOIN users learner ON ai.learner_id = learner.user_id
            JOIN learning_outcomes lo ON ai.outcome_id = lo.outcome_id
            ORDER BY ai.created_at DESC LIMIT 30
        """)
        explanations = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("teacher/ai_insights.html", recommendations=recommendations, explanations=explanations)


@teacher_bp.route("/teacher/reports")
@role_required("teacher", "admin")
def reports():
    conn = get_db()
    try:
        overview = teacher_overview(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT ti.*, learner.full_name AS learner_name, lo.outcome_name
            FROM teacher_interventions ti
            JOIN users learner ON ti.learner_id = learner.user_id
            JOIN learning_outcomes lo ON ti.outcome_id = lo.outcome_id
            ORDER BY ti.created_at DESC LIMIT 50
        """)
        interventions = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)
    return render_template("teacher/reports.html", overview=overview, interventions=interventions)


@teacher_bp.route("/teacher/recommendation/<int:recommendation_id>/<action>", methods=["POST"])
@role_required("teacher", "admin")
def review_recommendation(recommendation_id, action):
    status = "Approved" if action == "approve" else "Overridden"
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE recommendations SET teacher_status = %s WHERE recommendation_id = %s",
            (status, recommendation_id)
        )
        cur.execute(
            "SELECT * FROM recommendations WHERE recommendation_id = %s",
            (recommendation_id,)
        )
        rec = cur.fetchone()
        if rec:
            note = request.form.get("intervention_note") or f"AI recommendation {status.lower()} by teacher."
            cur.execute("""
                INSERT INTO teacher_interventions
                    (teacher_id, learner_id, outcome_id, intervention_type, intervention_note, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session["user_id"], rec["learner_id"], rec["outcome_id"], status, note, "Recorded"))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash(f"Recommendation {status.lower()} and teacher intervention recorded.", "success")
    return redirect(url_for("teacher.teacher_dashboard"))


@teacher_bp.route("/teacher/practical-evidence")
@role_required("teacher", "admin")
def practical_evidence():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT pe.*, learner.full_name AS learner_name, lo.outcome_name, subjects.subject_name
            FROM practical_evidence pe
            JOIN users learner ON pe.learner_id = learner.user_id
            JOIN learning_outcomes lo ON pe.outcome_id = lo.outcome_id
            JOIN competencies c ON lo.competency_id = c.competency_id
            JOIN subjects ON c.subject_id = subjects.subject_id
            ORDER BY pe.created_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    # Attach signed URLs for private Supabase Storage files
    rows_with_urls = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("file_path"):
            row_dict["signed_url"] = _get_signed_url(row_dict["file_path"])
        else:
            row_dict["signed_url"] = None
        rows_with_urls.append(row_dict)

    return render_template("teacher/practical_evidence.html", rows=rows_with_urls)


@teacher_bp.route("/teacher/practical-evidence/<int:practical_id>/<action>", methods=["POST"])
@role_required("teacher", "admin")
def review_practical_evidence(practical_id, action):
    status  = "Approved" if action == "approve" else "Needs Revision"
    comment = request.form.get("teacher_comment") or (
        "Evidence approved." if action == "approve" else "Revise and resubmit evidence."
    )

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM practical_evidence WHERE practical_id = %s", (practical_id,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE practical_evidence
                SET teacher_status = %s, teacher_comment = %s, reviewed_at = NOW()
                WHERE practical_id = %s
            """, (status, comment, practical_id))
            cur.execute("""
                INSERT INTO teacher_interventions
                    (teacher_id, learner_id, outcome_id, intervention_type, intervention_note, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session["user_id"], row["learner_id"], row["outcome_id"],
                  "Practical Evidence Review", comment, status))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash(f"Practical evidence marked as {status}.", "success")
    return redirect(url_for("teacher.practical_evidence"))

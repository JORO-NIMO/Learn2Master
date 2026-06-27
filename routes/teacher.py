from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from routes.guards import role_required
from database import get_db
from services.analytics_engine import teacher_overview, recent_ai_recommendations

teacher_bp = Blueprint("teacher", __name__)


def learner_rows(conn):
    return conn.execute("""
        SELECT learner.user_id, learner.full_name, learner.username, learner.email,
               COALESCE(lp.class_level, 'Senior One') AS class_level,
               COALESCE(lp.learning_pace, 'Not classified') AS learning_pace,
               COALESCE(lp.learning_style, 'Adaptive / Mixed') AS learning_style,
               COUNT(mr.mastery_id) AS mastery_records,
               SUM(CASE WHEN mr.mastery_status='Mastered' THEN 1 ELSE 0 END) AS mastered_records,
               ROUND(AVG(COALESCE(mr.mastery_score, 0)), 1) AS avg_mastery
        FROM users learner
        JOIN roles r ON learner.role_id = r.role_id
        LEFT JOIN learner_profiles lp ON lp.learner_id = learner.user_id
        LEFT JOIN mastery_records mr ON mr.learner_id = learner.user_id
        WHERE r.role_name='student'
        GROUP BY learner.user_id
        ORDER BY learner.full_name
    """).fetchall()


@teacher_bp.route("/teacher")
@role_required("teacher", "admin")
def teacher_dashboard():
    conn = get_db()
    overview = teacher_overview(conn)
    recommendations = recent_ai_recommendations(conn)
    interventions = conn.execute("""
        SELECT ti.*, learner.full_name AS learner_name, lo.outcome_name
        FROM teacher_interventions ti
        JOIN users learner ON ti.learner_id = learner.user_id
        JOIN learning_outcomes lo ON ti.outcome_id = lo.outcome_id
        ORDER BY ti.created_at DESC LIMIT 8
    """).fetchall()
    weak = conn.execute("""
        SELECT cm.concept_tag, ROUND(AVG(cm.latest_score),1) AS avg_score, COUNT(*) AS evidence
        FROM concept_mastery cm
        GROUP BY cm.concept_tag
        ORDER BY avg_score ASC
        LIMIT 6
    """).fetchall()
    conn.close()
    return render_template("teacher/dashboard.html", overview=overview, recommendations=recommendations, interventions=interventions, weak=weak)


@teacher_bp.route("/teacher/learners")
@role_required("teacher", "admin")
def learners():
    conn = get_db()
    rows = learner_rows(conn)
    conn.close()
    return render_template("teacher/learners.html", learners=rows)


@teacher_bp.route("/teacher/mastery-monitor")
@role_required("teacher", "admin")
def mastery_monitor():
    conn = get_db()
    rows = conn.execute("""
        SELECT learner.full_name, subjects.subject_name, lo.outcome_code, lo.outcome_name,
               COALESCE(mr.pretest_score,0) AS pretest_score,
               COALESCE(mr.practice_score,0) AS practice_score,
               COALESCE(mr.posttest_score,0) AS posttest_score,
               COALESCE(mr.mastery_score,0) AS mastery_score,
               COALESCE(mr.mastery_level,'Beginning') AS mastery_level,
               COALESCE(mr.mastery_status,'Not Started') AS mastery_status
        FROM learning_outcomes lo
        JOIN competencies c ON lo.competency_id=c.competency_id
        JOIN subjects ON c.subject_id=subjects.subject_id
        CROSS JOIN users learner
        JOIN roles r ON learner.role_id=r.role_id AND r.role_name='student'
        LEFT JOIN mastery_records mr ON mr.outcome_id=lo.outcome_id AND mr.learner_id=learner.user_id
        ORDER BY learner.full_name, subjects.subject_name, lo.sequence_order
    """).fetchall()
    conn.close()
    return render_template("teacher/mastery_monitor.html", rows=rows)


@teacher_bp.route("/teacher/ai-insights")
@role_required("teacher", "admin")
def ai_insights():
    conn = get_db()
    recommendations = recent_ai_recommendations(conn, limit=30)
    explanations = conn.execute("""
        SELECT ai.*, learner.full_name, lo.outcome_name
        FROM ai_explanations ai
        JOIN users learner ON ai.learner_id=learner.user_id
        JOIN learning_outcomes lo ON ai.outcome_id=lo.outcome_id
        ORDER BY ai.created_at DESC LIMIT 30
    """).fetchall()
    conn.close()
    return render_template("teacher/ai_insights.html", recommendations=recommendations, explanations=explanations)


@teacher_bp.route("/teacher/reports")
@role_required("teacher", "admin")
def reports():
    conn = get_db()
    overview = teacher_overview(conn)
    interventions = conn.execute("""
        SELECT ti.*, learner.full_name AS learner_name, lo.outcome_name
        FROM teacher_interventions ti
        JOIN users learner ON ti.learner_id=learner.user_id
        JOIN learning_outcomes lo ON ti.outcome_id=lo.outcome_id
        ORDER BY ti.created_at DESC LIMIT 50
    """).fetchall()
    conn.close()
    return render_template("teacher/reports.html", overview=overview, interventions=interventions)


@teacher_bp.route("/teacher/recommendation/<int:recommendation_id>/<action>", methods=["POST"])
@role_required("teacher", "admin")
def review_recommendation(recommendation_id, action):
    status = "Approved" if action == "approve" else "Overridden"
    conn = get_db()
    conn.execute("UPDATE recommendations SET teacher_status = ? WHERE recommendation_id = ?", (status, recommendation_id))
    rec = conn.execute("SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)).fetchone()
    if rec:
        note = request.form.get("intervention_note") or f"AI recommendation {status.lower()} by teacher."
        conn.execute("""
            INSERT INTO teacher_interventions (teacher_id, learner_id, outcome_id, intervention_type, intervention_note, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session["user_id"], rec["learner_id"], rec["outcome_id"], status, note, "Recorded"))
    conn.commit(); conn.close()
    flash(f"Recommendation {status.lower()} and teacher intervention recorded.", "success")
    return redirect(url_for("teacher.teacher_dashboard"))


@teacher_bp.route("/teacher/practical-evidence")
@role_required("teacher", "admin")
def practical_evidence():
    conn = get_db()
    rows = conn.execute("""
        SELECT pe.*, learner.full_name AS learner_name, lo.outcome_name, subjects.subject_name
        FROM practical_evidence pe
        JOIN users learner ON pe.learner_id = learner.user_id
        JOIN learning_outcomes lo ON pe.outcome_id = lo.outcome_id
        JOIN competencies c ON lo.competency_id = c.competency_id
        JOIN subjects ON c.subject_id = subjects.subject_id
        ORDER BY pe.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("teacher/practical_evidence.html", rows=rows)


@teacher_bp.route("/teacher/practical-evidence/<int:practical_id>/<action>", methods=["POST"])
@role_required("teacher", "admin")
def review_practical_evidence(practical_id, action):
    status = "Approved" if action == "approve" else "Needs Revision"
    comment = request.form.get("teacher_comment") or ("Evidence approved." if action == "approve" else "Revise and resubmit evidence.")
    conn = get_db()
    row = conn.execute("SELECT * FROM practical_evidence WHERE practical_id=?", (practical_id,)).fetchone()
    if row:
        conn.execute("""
            UPDATE practical_evidence
            SET teacher_status=?, teacher_comment=?, reviewed_at=CURRENT_TIMESTAMP
            WHERE practical_id=?
        """, (status, comment, practical_id))
        conn.execute("""
            INSERT INTO teacher_interventions (teacher_id, learner_id, outcome_id, intervention_type, intervention_note, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session["user_id"], row["learner_id"], row["outcome_id"], "Practical Evidence Review", comment, status))
    conn.commit(); conn.close()
    flash(f"Practical evidence marked as {status}.", "success")
    return redirect(url_for("teacher.practical_evidence"))

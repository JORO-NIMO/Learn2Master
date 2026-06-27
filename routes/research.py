from flask import Blueprint, render_template
from routes.guards import role_required
from database import get_db

research_bp = Blueprint("research", __name__)


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row and row[0] is not None else 0


@research_bp.route("/research-dashboard")
@role_required("admin", "teacher")
def research_dashboard():
    conn = get_db()
    metrics = {
        "learners": one(conn, "SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='student'"),
        "attempts": one(conn, "SELECT COUNT(*) FROM assessment_attempts"),
        "mastery_records": one(conn, "SELECT COUNT(*) FROM mastery_records"),
        "mastered": one(conn, "SELECT COUNT(*) FROM mastery_records WHERE mastery_status='Mastered'"),
        "avg_pretest": one(conn, "SELECT ROUND(AVG(pretest_score),1) FROM mastery_records"),
        "avg_posttest": one(conn, "SELECT ROUND(AVG(posttest_score),1) FROM mastery_records"),
        "avg_mastery": one(conn, "SELECT ROUND(AVG(mastery_score),1) FROM mastery_records"),
        "teacher_interventions": one(conn, "SELECT COUNT(*) FROM teacher_interventions"),
        "ai_recommendations": one(conn, "SELECT COUNT(*) FROM recommendations"),
        "reflections": one(conn, "SELECT COUNT(*) FROM learning_reflections"),
        "practical_evidence": one(conn, "SELECT COUNT(*) FROM practical_evidence"),
        "approved_practical": one(conn, "SELECT COUNT(*) FROM practical_evidence WHERE teacher_status='Approved'"),
        "bkt_observations": one(conn, "SELECT COALESCE(SUM(observations),0) FROM bkt_mastery"),
        "avg_bkt_mastery": one(conn, "SELECT ROUND(AVG(probability_mastery)*100,1) FROM bkt_mastery"),
        "offline_pending": one(conn, "SELECT COUNT(*) FROM offline_sync_queue WHERE sync_status='Pending'"),
    }
    metrics["learning_gain"] = round(float(metrics["avg_posttest"] or 0) - float(metrics["avg_pretest"] or 0), 1)
    metrics["mastery_rate"] = round((metrics["mastered"] / metrics["mastery_records"] * 100), 1) if metrics["mastery_records"] else 0
    weak_concepts = conn.execute("""
        SELECT concept_tag, ROUND(AVG(latest_score),1) AS avg_score, COUNT(*) AS evidence
        FROM concept_mastery
        GROUP BY concept_tag
        ORDER BY avg_score ASC
        LIMIT 8
    """).fetchall()
    conn.close()
    return render_template("research/dashboard.html", metrics=metrics, weak_concepts=weak_concepts)

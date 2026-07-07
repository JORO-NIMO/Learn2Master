"""routes/research.py — Research dashboard route (Supabase/PostgreSQL edition)."""
from flask import Blueprint, render_template
from routes.guards import role_required
from database import get_db, release_db

research_bp = Blueprint("research", __name__)


def _one(cur, sql, params=()):
    """Execute a scalar-returning query and return the value (0 if NULL/missing)."""
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return 0
    val = list(row.values())[0]
    return val if val is not None else 0


@research_bp.route("/research-dashboard")
@role_required("admin", "teacher")
def research_dashboard():
    conn = get_db()
    try:
        cur = conn.cursor()

        metrics = {
            "learners": _one(cur,
                "SELECT COUNT(*) FROM users JOIN roles ON users.role_id=roles.role_id WHERE roles.role_name='student'"),
            "attempts":            _one(cur, "SELECT COUNT(*) FROM assessment_attempts"),
            "mastery_records":     _one(cur, "SELECT COUNT(*) FROM mastery_records"),
            "mastered":            _one(cur, "SELECT COUNT(*) FROM mastery_records WHERE mastery_status='Mastered'"),
            "avg_pretest":         _one(cur, "SELECT ROUND(AVG(pretest_score)::numeric, 1) FROM mastery_records"),
            "avg_posttest":        _one(cur, "SELECT ROUND(AVG(posttest_score)::numeric, 1) FROM mastery_records"),
            "avg_mastery":         _one(cur, "SELECT ROUND(AVG(mastery_score)::numeric, 1) FROM mastery_records"),
            "teacher_interventions": _one(cur, "SELECT COUNT(*) FROM teacher_interventions"),
            "ai_recommendations":  _one(cur, "SELECT COUNT(*) FROM recommendations"),
            "reflections":         _one(cur, "SELECT COUNT(*) FROM learning_reflections"),
            "practical_evidence":  _one(cur, "SELECT COUNT(*) FROM practical_evidence"),
            "approved_practical":  _one(cur, "SELECT COUNT(*) FROM practical_evidence WHERE teacher_status='Approved'"),
            "bkt_observations":    _one(cur, "SELECT COALESCE(SUM(observations),0) FROM bkt_mastery"),
            "avg_bkt_mastery":     _one(cur, "SELECT ROUND((AVG(probability_mastery)*100)::numeric, 1) FROM bkt_mastery"),
            "offline_pending":     _one(cur, "SELECT COUNT(*) FROM offline_sync_queue WHERE sync_status='Pending'"),
        }
        metrics["learning_gain"] = round(
            float(metrics["avg_posttest"] or 0) - float(metrics["avg_pretest"] or 0), 1
        )
        metrics["mastery_rate"] = (
            round((metrics["mastered"] / metrics["mastery_records"] * 100), 1)
            if metrics["mastery_records"] else 0
        )

        cur.execute("""
            SELECT concept_tag,
                   ROUND(AVG(latest_score)::numeric, 1) AS avg_score,
                   COUNT(*) AS evidence
            FROM concept_mastery
            GROUP BY concept_tag
            ORDER BY avg_score ASC
            LIMIT 8
        """)
        weak_concepts = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    return render_template("research/dashboard.html", metrics=metrics, weak_concepts=weak_concepts)

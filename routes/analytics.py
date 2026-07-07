"""routes/analytics.py — Analytics dashboard route (Supabase/PostgreSQL edition)."""
from flask import Blueprint, render_template
from routes.guards import role_required
from database import get_db, release_db
from services.analytics_engine import teacher_overview, framework_metrics, recent_ai_recommendations

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@role_required("teacher", "admin")
def analytics_dashboard():
    conn = get_db()
    try:
        overview        = teacher_overview(conn)
        metrics         = framework_metrics(conn)
        recommendations = recent_ai_recommendations(conn, limit=10)

        cur = conn.cursor()
        cur.execute("""
            SELECT concept_tag, AVG(latest_score) AS avg_score, COUNT(*) AS attempts
            FROM concept_mastery
            GROUP BY concept_tag
            ORDER BY avg_score ASC
        """)
        concept_rows = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "analytics.html",
        overview=overview,
        metrics=metrics,
        recommendations=recommendations,
        concept_rows=concept_rows,
    )

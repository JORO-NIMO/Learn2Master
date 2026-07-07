"""services/analytics_engine.py — Analytics queries (Supabase/PostgreSQL edition).

All computations that were previously done in Python by fetching entire tables
are now pushed to PostgreSQL aggregation queries — reducing memory usage and
round-trips on the teacher and analytics dashboards.
"""
from collections import Counter


def safe_percent(numerator, denominator):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100, 1)


def teacher_overview(conn):
    """
    Returns a summary dict for the teacher dashboard.
    Aggregation happens in PostgreSQL — no full-table fetch into Python.
    """
    cur = conn.cursor()

    # Learner count
    cur.execute("""
        SELECT COUNT(*) AS total FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE r.role_name = 'student'
    """)
    learners = cur.fetchone()["total"]

    # Mastered / at-risk / avg — single aggregation query
    cur.execute("""
        SELECT
            COUNT(*)                                                        AS total_records,
            SUM(CASE WHEN mastery_status = 'Mastered' THEN 1 ELSE 0 END)   AS mastered,
            SUM(CASE WHEN mastery_status != 'Mastered'
                      AND (posttest_score + practice_score + pretest_score) > 0
                 THEN 1 ELSE 0 END)                                         AS at_risk,
            COALESCE(ROUND(AVG(mastery_score)::numeric, 1), 0)              AS avg_mastery
        FROM mastery_records
    """)
    agg = cur.fetchone()
    total_records = agg["total_records"] or 0
    mastered      = agg["mastered"]      or 0
    at_risk       = agg["at_risk"]       or 0
    avg_mastery   = float(agg["avg_mastery"] or 0)

    # Pending reviews
    cur.execute("""
        SELECT COUNT(*) AS total FROM recommendations
        WHERE teacher_status = 'Pending Review'
    """)
    pending_recs = cur.fetchone()["total"]

    # Most common weak concept
    cur.execute("""
        SELECT concept_tag, COUNT(*) AS freq
        FROM concept_mastery
        WHERE latest_score < 70
        GROUP BY concept_tag
        ORDER BY freq DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    common_weak = row["concept_tag"].replace("_", " ").title() if row else "None currently"

    # Recent records for template iteration (kept for backwards compatibility)
    cur.execute("""
        SELECT mr.mastery_status, mr.mastery_score, mr.posttest_score,
               mr.practice_score, mr.pretest_score,
               u.full_name, lo.outcome_name
        FROM mastery_records mr
        JOIN users u  ON mr.learner_id = u.user_id
        JOIN learning_outcomes lo ON mr.outcome_id = lo.outcome_id
        ORDER BY mr.updated_at DESC
        LIMIT 200
    """)
    records = cur.fetchall()
    cur.close()

    return {
        "learners":     learners,
        "records":      records,
        "mastered":     mastered,
        "at_risk":      at_risk,
        "avg_mastery":  avg_mastery,
        "pending_recs": pending_recs,
        "mastery_rate": safe_percent(mastered, total_records),
        "common_weak":  common_weak,
    }


def recent_ai_recommendations(conn, limit=8):
    cur = conn.cursor()
    cur.execute("""
        SELECT rec.*, u.full_name, lo.outcome_name
        FROM recommendations rec
        JOIN users u  ON rec.learner_id = u.user_id
        JOIN learning_outcomes lo ON rec.outcome_id = lo.outcome_id
        ORDER BY rec.created_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    return rows


def framework_metrics(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT
            (SELECT COUNT(*) FROM learning_outcomes)                                  AS total_outcomes,
            (SELECT COUNT(*) FROM recommendations)                                    AS total_recommendations,
            (SELECT COUNT(*) FROM assessment_attempts)                                AS total_attempts,
            (SELECT COUNT(*) FROM mastery_records WHERE mastery_status = 'Mastered') AS mastered_records,
            (SELECT COUNT(*) FROM mastery_records)                                    AS total_records
    """)
    row = cur.fetchone()
    cur.close()

    total_records = row["total_records"] or 0
    mastered      = row["mastered_records"] or 0

    return {
        "total_outcomes":        row["total_outcomes"],
        "total_recommendations": row["total_recommendations"],
        "total_attempts":        row["total_attempts"],
        "mastered_records":      mastered,
        "mastery_rate":          safe_percent(mastered, total_records),
    }

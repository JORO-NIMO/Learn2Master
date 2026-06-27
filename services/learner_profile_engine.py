from collections import Counter


def learner_profile(conn, learner_id):
    user = conn.execute("""
        SELECT u.*, s.school_name
        FROM users u
        LEFT JOIN schools s ON u.school_id = s.school_id
        WHERE u.user_id = ?
    """, (learner_id,)).fetchone()

    profile = conn.execute("SELECT * FROM learner_profiles WHERE learner_id = ?", (learner_id,)).fetchone()
    records = conn.execute("""
        SELECT mr.*, lo.outcome_name, c.course_title, sub.subject_name
        FROM mastery_records mr
        JOIN learning_outcomes lo ON mr.outcome_id = lo.outcome_id
        JOIN competencies comp ON lo.competency_id = comp.competency_id
        JOIN subjects sub ON comp.subject_id = sub.subject_id
        LEFT JOIN lessons l ON l.outcome_id = lo.outcome_id
        LEFT JOIN courses c ON l.course_id = c.course_id
        WHERE mr.learner_id = ?
        ORDER BY mr.updated_at DESC
    """, (learner_id,)).fetchall()

    concepts = conn.execute("""
        SELECT concept_tag, latest_score, concept_status, attempt_count
        FROM concept_mastery
        WHERE learner_id = ?
        ORDER BY latest_score ASC, attempt_count DESC
    """, (learner_id,)).fetchall()

    attempts = conn.execute("SELECT COUNT(*) AS total FROM assessment_attempts WHERE learner_id = ?", (learner_id,)).fetchone()["total"]
    logs = conn.execute("SELECT * FROM activity_logs WHERE learner_id = ? ORDER BY created_at DESC LIMIT 8", (learner_id,)).fetchall()

    avg_mastery = round(sum(r["mastery_score"] for r in records) / len(records), 1) if records else 0
    mastered = sum(1 for r in records if r["mastery_status"] == "Mastered")
    weak = [c for c in concepts if c["latest_score"] < 70]
    strong = [c for c in concepts if c["latest_score"] >= 70]

    if attempts <= 2:
        pace = "New learner"
    elif avg_mastery >= 85:
        pace = "Fast / High mastery"
    elif avg_mastery >= 65:
        pace = "Moderate"
    else:
        pace = "Needs guided support"

    summary = (
        f"This learner has completed {attempts} assessment attempt(s), mastered {mastered} outcome record(s), "
        f"and currently has an AI confidence average of {avg_mastery}%."
    )

    return {
        "user": user,
        "profile": profile,
        "records": records,
        "concepts": concepts,
        "weak_concepts": weak[:5],
        "strong_concepts": strong[:5],
        "attempts": attempts,
        "avg_mastery": avg_mastery,
        "mastered": mastered,
        "learning_pace": pace,
        "ai_summary": summary,
        "logs": logs,
    }

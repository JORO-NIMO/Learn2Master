"""services/evidence_engine.py — Evidence and reflection queries (Supabase/PostgreSQL edition)."""


def has_reflection(conn, learner_id, outcome_id) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT reflection_id FROM learning_reflections
        WHERE learner_id = %s AND outcome_id = %s
        ORDER BY created_at DESC LIMIT 1
    """, (learner_id, outcome_id))
    row = cur.fetchone()
    cur.close()
    return bool(row)


def latest_reflection(conn, learner_id, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM learning_reflections
        WHERE learner_id = %s AND outcome_id = %s
        ORDER BY created_at DESC LIMIT 1
    """, (learner_id, outcome_id))
    row = cur.fetchone()
    cur.close()
    return row


def evidence_checklist(
    pretest_attempt, practice_attempt, posttest_attempt,
    weak_resolved, reflection_done, posttest_score, threshold
):
    return {
        "pretest_completed":          bool(pretest_attempt),
        "adaptive_practice_completed": bool(practice_attempt),
        "weak_concepts_resolved":     bool(weak_resolved),
        "reflection_completed":       bool(reflection_done),
        "posttest_completed":         bool(posttest_attempt),
        "posttest_passed":            bool(posttest_attempt and posttest_score >= threshold),
    }


def record_ai_explanation(
    conn, learner_id, outcome_id,
    decision_type, evidence_used, explanation_text, confidence_score
):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ai_explanations
            (learner_id, outcome_id, decision_type, evidence_used, explanation_text, confidence_score)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (learner_id, outcome_id, decision_type, evidence_used, explanation_text, confidence_score))
    cur.close()

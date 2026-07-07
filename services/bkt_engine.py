"""
services/bkt_engine.py — Simplified Bayesian Knowledge Tracing engine (Supabase/PostgreSQL edition).

Pure maths functions are unchanged. SQL uses %s placeholders and cursor pattern.
CURRENT_TIMESTAMP replaced with NOW().
"""


def update_bkt(p_mastery, correct, p_learn=0.12, p_slip=0.10, p_guess=0.20):
    p_mastery = max(0.0, min(1.0, float(p_mastery)))
    if correct:
        numerator   = p_mastery * (1 - p_slip)
        denominator = numerator + (1 - p_mastery) * p_guess
    else:
        numerator   = p_mastery * p_slip
        denominator = numerator + (1 - p_mastery) * (1 - p_guess)
    posterior = numerator / denominator if denominator else p_mastery
    return round(posterior + (1 - posterior) * p_learn, 4)


def concept_confidence(score, attempts=1):
    base           = max(0, min(100, float(score))) / 100
    attempt_factor = min(1, attempts / 3)
    return round((base * 0.8 + attempt_factor * 0.2) * 100, 1)


def update_bkt_record(conn, learner_id, outcome_id, concept_tag, correct):
    cur = conn.cursor()
    cur.execute("""
        SELECT probability_mastery, observations
        FROM bkt_mastery
        WHERE learner_id = %s AND outcome_id = %s AND concept_tag = %s
    """, (learner_id, outcome_id, concept_tag))
    row          = cur.fetchone()
    current      = row["probability_mastery"] if row else 0.20
    observations = row["observations"]        if row else 0
    updated      = update_bkt(current, correct)

    cur.execute("""
        INSERT INTO bkt_mastery
            (learner_id, outcome_id, concept_tag, probability_mastery, observations)
        VALUES (%s, %s, %s, %s, 1)
        ON CONFLICT (learner_id, outcome_id, concept_tag)
        DO UPDATE SET
            probability_mastery = EXCLUDED.probability_mastery,
            observations        = bkt_mastery.observations + 1,
            updated_at          = NOW()
    """, (learner_id, outcome_id, concept_tag, updated))
    cur.close()
    return updated, observations + 1


def bkt_summary(conn, learner_id, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT concept_tag, probability_mastery, observations
        FROM bkt_mastery
        WHERE learner_id = %s AND outcome_id = %s
        ORDER BY concept_tag
    """, (learner_id, outcome_id))
    rows = cur.fetchall()
    cur.close()
    return rows

"""Simplified Bayesian Knowledge Tracing engine for Learn2Master V8.
Transparent, explainable and suitable for dissertation demonstration.
"""


def update_bkt(p_mastery, correct, p_learn=0.12, p_slip=0.10, p_guess=0.20):
    p_mastery = max(0.0, min(1.0, float(p_mastery)))
    if correct:
        numerator = p_mastery * (1 - p_slip)
        denominator = numerator + (1 - p_mastery) * p_guess
    else:
        numerator = p_mastery * p_slip
        denominator = numerator + (1 - p_mastery) * (1 - p_guess)
    posterior = numerator / denominator if denominator else p_mastery
    return round(posterior + (1 - posterior) * p_learn, 4)


def concept_confidence(score, attempts=1):
    base = max(0, min(100, float(score))) / 100
    attempt_factor = min(1, attempts / 3)
    return round((base * 0.8 + attempt_factor * 0.2) * 100, 1)


def update_bkt_record(conn, learner_id, outcome_id, concept_tag, correct):
    row = conn.execute("""
        SELECT probability_mastery, observations
        FROM bkt_mastery
        WHERE learner_id=? AND outcome_id=? AND concept_tag=?
    """, (learner_id, outcome_id, concept_tag)).fetchone()
    current = row["probability_mastery"] if row else 0.20
    observations = row["observations"] if row else 0
    updated = update_bkt(current, correct)
    conn.execute("""
        INSERT INTO bkt_mastery (learner_id, outcome_id, concept_tag, probability_mastery, observations)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(learner_id, outcome_id, concept_tag)
        DO UPDATE SET
            probability_mastery=excluded.probability_mastery,
            observations=bkt_mastery.observations + 1,
            updated_at=CURRENT_TIMESTAMP
    """, (learner_id, outcome_id, concept_tag, updated))
    return updated, observations + 1


def bkt_summary(conn, learner_id, outcome_id):
    rows = conn.execute("""
        SELECT concept_tag, probability_mastery, observations
        FROM bkt_mastery
        WHERE learner_id=? AND outcome_id=?
        ORDER BY concept_tag
    """, (learner_id, outcome_id)).fetchall()
    return rows

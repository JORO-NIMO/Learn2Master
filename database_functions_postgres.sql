-- ============================================================
-- Learn2Master V8 — PostgreSQL Utility Functions
-- Run in Supabase SQL Editor AFTER database_v2_postgres.sql
-- ============================================================

-- ── 1. get_learner_dashboard_stats ───────────────────────────
-- Replaces 6 separate COUNT/AVG queries on the student dashboard
-- with a single round-trip. Returns a JSON record.

CREATE OR REPLACE FUNCTION get_learner_dashboard_stats(p_learner_id INTEGER)
RETURNS TABLE (
    total_outcomes      BIGINT,
    mastered_outcomes   BIGINT,
    attempted_outcomes  BIGINT,
    avg_mastery         NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM learning_outcomes)::BIGINT                            AS total_outcomes,
        (SELECT COUNT(*) FROM mastery_records
         WHERE learner_id = p_learner_id AND mastery_status = 'Mastered')::BIGINT  AS mastered_outcomes,
        (SELECT COUNT(DISTINCT lo.outcome_id)
         FROM assessment_attempts aa
         JOIN assessments a  ON aa.assessment_id = a.assessment_id
         JOIN lessons l      ON a.lesson_id = l.lesson_id
         JOIN learning_outcomes lo ON l.outcome_id = lo.outcome_id
         WHERE aa.learner_id = p_learner_id)::BIGINT                               AS attempted_outcomes,
        COALESCE(
            (SELECT ROUND(AVG(mastery_score)::NUMERIC, 1)
             FROM mastery_records WHERE learner_id = p_learner_id),
            0
        )                                                                           AS avg_mastery;
END;
$$ LANGUAGE plpgsql STABLE;

-- ── 2. unlock_next_outcome ───────────────────────────────────
-- Atomically marks the next sequential outcome as unlocked
-- when a learner achieves mastery on the current one.

CREATE OR REPLACE FUNCTION unlock_next_outcome(
    p_learner_id  INTEGER,
    p_outcome_id  INTEGER
) RETURNS VOID AS $$
DECLARE
    v_next_id INTEGER;
BEGIN
    SELECT next.outcome_id INTO v_next_id
    FROM learning_outcomes current
    JOIN learning_outcomes next
        ON next.competency_id  = current.competency_id
       AND next.sequence_order = current.sequence_order + 1
    WHERE current.outcome_id = p_outcome_id;

    IF v_next_id IS NOT NULL THEN
        INSERT INTO mastery_records
            (learner_id, outcome_id, mastery_score, mastery_level, mastery_status, is_unlocked)
        VALUES (p_learner_id, v_next_id, 0, 'Beginning', 'Not Started', TRUE)
        ON CONFLICT (learner_id, outcome_id)
        DO UPDATE SET is_unlocked = TRUE, updated_at = NOW();
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ── 3. update_bkt_probability ────────────────────────────────
-- Runs BKT update calculation entirely in the database,
-- eliminating one round-trip per question answered.

CREATE OR REPLACE FUNCTION update_bkt_probability(
    p_learner_id  INTEGER,
    p_outcome_id  INTEGER,
    p_concept     TEXT,
    p_correct     BOOLEAN
) RETURNS NUMERIC AS $$
DECLARE
    v_current   NUMERIC := 0.20;
    v_posterior NUMERIC;
    v_updated   NUMERIC;
    p_learn     NUMERIC := 0.12;
    p_slip      NUMERIC := 0.10;
    p_guess     NUMERIC := 0.20;
    v_num       NUMERIC;
    v_den       NUMERIC;
BEGIN
    SELECT probability_mastery INTO v_current
    FROM bkt_mastery
    WHERE learner_id = p_learner_id
      AND outcome_id = p_outcome_id
      AND concept_tag = p_concept;

    IF v_current IS NULL THEN v_current := 0.20; END IF;
    v_current := GREATEST(0.0, LEAST(1.0, v_current));

    IF p_correct THEN
        v_num := v_current * (1 - p_slip);
        v_den := v_num + (1 - v_current) * p_guess;
    ELSE
        v_num := v_current * p_slip;
        v_den := v_num + (1 - v_current) * (1 - p_guess);
    END IF;

    v_posterior := CASE WHEN v_den > 0 THEN v_num / v_den ELSE v_current END;
    v_updated   := ROUND((v_posterior + (1 - v_posterior) * p_learn)::NUMERIC, 4);

    INSERT INTO bkt_mastery
        (learner_id, outcome_id, concept_tag, probability_mastery, observations)
    VALUES (p_learner_id, p_outcome_id, p_concept, v_updated, 1)
    ON CONFLICT (learner_id, outcome_id, concept_tag)
    DO UPDATE SET
        probability_mastery = v_updated,
        observations        = bkt_mastery.observations + 1,
        updated_at          = NOW();

    RETURN v_updated;
END;
$$ LANGUAGE plpgsql;

-- ── 4. get_teacher_overview ──────────────────────────────────
-- Returns key teacher dashboard metrics in a single query
-- instead of the 4 separate queries in analytics_engine.py.

CREATE OR REPLACE FUNCTION get_teacher_overview()
RETURNS TABLE (
    total_learners      BIGINT,
    total_mastered      BIGINT,
    total_at_risk       BIGINT,
    avg_mastery_score   NUMERIC,
    pending_reviews     BIGINT,
    mastery_rate        NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM users u
         JOIN roles r ON u.role_id = r.role_id
         WHERE r.role_name = 'student')::BIGINT                         AS total_learners,
        (SELECT COUNT(*) FROM mastery_records
         WHERE mastery_status = 'Mastered')::BIGINT                     AS total_mastered,
        (SELECT COUNT(*) FROM mastery_records
         WHERE mastery_status != 'Mastered'
           AND (posttest_score + practice_score + pretest_score) > 0
        )::BIGINT                                                        AS total_at_risk,
        COALESCE(
            (SELECT ROUND(AVG(mastery_score)::NUMERIC, 1) FROM mastery_records), 0
        )                                                                AS avg_mastery_score,
        (SELECT COUNT(*) FROM recommendations
         WHERE teacher_status = 'Pending Review')::BIGINT               AS pending_reviews,
        CASE
            WHEN (SELECT COUNT(*) FROM mastery_records) > 0
            THEN ROUND(
                (SELECT COUNT(*) FROM mastery_records WHERE mastery_status = 'Mastered')::NUMERIC
                / (SELECT COUNT(*) FROM mastery_records)::NUMERIC * 100, 1)
            ELSE 0
        END                                                              AS mastery_rate;
END;
$$ LANGUAGE plpgsql STABLE;

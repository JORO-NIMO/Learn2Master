"""
routes/sync.py — Offline Assessment Sync Endpoint for Learn2Master.

Accepts queued assessment submissions from the browser's IndexedDB when the
learner reconnects. Runs the same grading logic as routes/learning.submit_assessment
so offline submissions produce identical mastery records to live submissions.

This blueprint is CSRF-exempt from global Flask-WTF middleware (see app.py:
    csrf.exempt(sync_bp)
) because it is a JSON API endpoint. Instead, it reads and validates the
csrf_token from the JSON request body directly.
"""

import json
from collections import defaultdict

from flask import Blueprint, request, jsonify, session
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError

from database import get_db, release_db
from routes.learning import (
    update_concept_mastery,
    update_bkt_record,
    posttest_unlock_status,
    get_required_concepts,
)
from services.mastery_engine import calculate_percentage, mastery_level
from services.bkt_engine import update_bkt_record  # noqa: F811 — re-export alias

sync_bp = Blueprint("sync", __name__)

PRACTICE_CONCEPT_THRESHOLD = 70  # mirrors routes/learning constant


# ── Internal: process one sync item ──────────────────────────────────────────

def _process_sync_item(conn, learner_id, item):
    """Grade a single offline assessment submission.

    Replicates routes/learning.submit_assessment logic, reading answers from
    the JSON payload dict instead of request.form.

    All DB writes use the caller's conn. The caller commits or rolls back.
    Raises on any error so the caller can record a 'Failed' row.
    """
    assessment_id = int(item["_assessment_id"])

    cur = conn.cursor()

    # Fetch assessment + lesson + outcome context
    cur.execute("""
        SELECT assessments.*,
               lessons.outcome_id,
               lessons.lesson_id,
               lo.outcome_name,
               lo.mastery_threshold
        FROM assessments
        JOIN lessons ON assessments.lesson_id = lessons.lesson_id
        JOIN learning_outcomes lo ON lessons.outcome_id = lo.outcome_id
        WHERE assessments.assessment_id = %s
    """, (assessment_id,))
    assessment = cur.fetchone()
    if not assessment:
        cur.close()
        raise ValueError(f"Assessment {assessment_id} not found")

    outcome_id       = assessment["outcome_id"]
    assessment_type  = assessment["assessment_type"]
    mastery_threshold = assessment["mastery_threshold"]

    # Build answer map from payload keys: question_<id> → selected_option_id
    answer_map = {}
    for k, v in item.items():
        if k.startswith("question_"):
            try:
                qid = int(k.split("_", 1)[1])
                answer_map[qid] = int(v)
            except (ValueError, IndexError):
                continue

    # Fetch all questions for this assessment
    cur.execute("""
        SELECT question_id, question_text, concept_tag, marks
        FROM questions
        WHERE assessment_id = %s
        ORDER BY question_id
    """, (assessment_id,))
    questions = cur.fetchall()

    # Insert attempt shell — capture attempt_id via RETURNING
    cur.execute("""
        INSERT INTO assessment_attempts (learner_id, assessment_id, score, weak_concepts)
        VALUES (%s, %s, 0, '')
        RETURNING attempt_id
    """, (learner_id, assessment_id))
    attempt_id = cur.fetchone()["attempt_id"]

    # Grade each question
    correct_count      = 0
    weak_concepts      = []
    answered_questions = []
    concept_stats      = defaultdict(lambda: {"correct": 0, "total": 0})

    for q in questions:
        selected_option_id = answer_map.get(q["question_id"])
        if selected_option_id is None:
            continue

        cur.execute("""
            SELECT option_id FROM question_options
            WHERE question_id = %s AND is_correct = TRUE LIMIT 1
        """, (q["question_id"],))
        correct_opt = cur.fetchone()
        is_correct = bool(correct_opt and selected_option_id == correct_opt["option_id"])

        answered_questions.append(q)
        concept_stats[q["concept_tag"]]["total"] += 1
        if is_correct:
            correct_count += 1
            concept_stats[q["concept_tag"]]["correct"] += 1
        else:
            weak_concepts.append(q["concept_tag"])

        cur.execute("""
            INSERT INTO attempt_answers
                (attempt_id, question_id, selected_option_id, is_correct)
            VALUES (%s, %s, %s, %s)
        """, (attempt_id, q["question_id"], selected_option_id, is_correct))

        update_bkt_record(conn, learner_id, outcome_id, q["concept_tag"], is_correct)

    weak_concepts = sorted(set(weak_concepts))
    score = calculate_percentage(correct_count, len(answered_questions)) if answered_questions else 0

    cur.execute(
        "UPDATE assessment_attempts SET score = %s, weak_concepts = %s WHERE attempt_id = %s",
        (score, ",".join(weak_concepts), attempt_id)
    )

    # Update concept-level mastery
    update_concept_mastery(conn, learner_id, outcome_id, assessment_type, concept_stats)

    # Retrieve or initialise current mastery record
    cur.execute("""
        SELECT * FROM mastery_records
        WHERE learner_id = %s AND outcome_id = %s
    """, (learner_id, outcome_id))
    existing = cur.fetchone()

    pre      = existing["pretest_score"]     if existing else 0
    practice = existing["practice_score"]    if existing else 0
    post     = existing["posttest_score"]    if existing else 0
    m_score  = existing["mastery_score"]     if existing else 0
    improve  = existing["improvement_score"] if existing else 0
    status   = existing["mastery_status"]    if existing else "In Progress"
    level    = existing["mastery_level"]     if existing else "Beginning"

    required_concepts = get_required_concepts(conn, outcome_id)

    if assessment_type == "pretest":
        pre    = score
        status = "Adaptive Practice Required"
        level  = mastery_level(score)

    elif assessment_type == "practice":
        practice = score
        unlocked, not_ready = posttest_unlock_status(
            conn, learner_id, outcome_id, required_concepts
        )
        status = "Ready for Post-test" if unlocked else "Concept Practice Required"
        level  = mastery_level(score)
        weak_concepts = not_ready  # update weak_concepts for mastery record

    elif assessment_type == "posttest":
        post = score
        # Simple mastery score: weighted average of practice + posttest
        m_score = round((practice * 0.35) + (post * 0.65))
        m_score = min(100, m_score)
        improve = round(post - pre) if pre else 0
        level   = mastery_level(post)
        status  = "Mastered" if post >= mastery_threshold else "Remediation Required"

    # Upsert mastery record
    cur.execute("""
        INSERT INTO mastery_records
            (learner_id, outcome_id, pretest_score, practice_score, posttest_score,
             improvement_score, mastery_score, mastery_level, mastery_status, is_unlocked)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        ON CONFLICT (learner_id, outcome_id)
        DO UPDATE SET
            pretest_score     = EXCLUDED.pretest_score,
            practice_score    = EXCLUDED.practice_score,
            posttest_score    = EXCLUDED.posttest_score,
            improvement_score = EXCLUDED.improvement_score,
            mastery_score     = EXCLUDED.mastery_score,
            mastery_level     = EXCLUDED.mastery_level,
            mastery_status    = EXCLUDED.mastery_status,
            is_unlocked       = TRUE,
            updated_at        = NOW()
    """, (
        learner_id, outcome_id, pre, practice, post,
        improve, m_score, level, status
    ))

    # Activity log
    cur.execute("""
        INSERT INTO activity_logs (learner_id, activity_type, activity_description)
        VALUES (%s, %s, %s)
    """, (
        learner_id,
        "Sync Submission Processed",
        f"Assessment {assessment_id} ({assessment_type}) synced. Score: {score}%."
    ))

    cur.close()


# ── Route: POST /sync ─────────────────────────────────────────────────────────

@sync_bp.route("/sync", methods=["POST"])
def sync():
    """Process queued offline assessment submissions.

    Expects a JSON body with either a single submission object or a batch
    under an 'items' key. Each item must include:
      - _assessment_id: int
      - learner_id: int (must match session['user_id'])
      - question_<id>: selected_option_id for each answered question
      - csrf_token: the Flask-WTF CSRF token for this session
      - event_type: 'assessment_submission'
    """
    # Auth guard — students only
    if session.get("role") != "student":
        return jsonify({"error": "Forbidden"}), 403

    learner_id = session["user_id"]

    # Parse JSON body
    body = request.get_json(force=True, silent=True) or {}

    # Validate CSRF token from JSON body
    try:
        validate_csrf(body.get("csrf_token"))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    # Support single-item payload or explicit batch array
    items = body.get("items") or [body]
    synced = 0

    for item in items:
        # Ownership check — learner cannot replay another learner's submissions
        try:
            item_learner_id = int(item.get("learner_id", -1))
        except (TypeError, ValueError):
            continue
        if item_learner_id != learner_id:
            continue

        conn = get_db()
        try:
            _process_sync_item(conn, learner_id, item)
            conn.commit()

            # Record successful sync in queue
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO offline_sync_queue
                    (learner_id, event_type, payload, sync_status, synced_at)
                VALUES (%s, %s, %s, 'Synced', NOW())
            """, (
                learner_id,
                item.get("event_type", "assessment_submission"),
                json.dumps(item),
            ))
            conn.commit()
            cur.close()
            synced += 1

        except Exception as exc:
            conn.rollback()
            # Record failed item — do not abort the batch
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO offline_sync_queue
                        (learner_id, event_type, payload, sync_status)
                    VALUES (%s, %s, %s, 'Failed')
                """, (
                    learner_id,
                    item.get("event_type", "unknown"),
                    json.dumps({"error": str(exc), "item": item}),
                ))
                conn.commit()
                cur.close()
            except Exception:
                conn.rollback()
        finally:
            release_db(conn)

    return jsonify({"synced": synced}), 200

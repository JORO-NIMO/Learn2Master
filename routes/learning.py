"""
routes/learning.py — Adaptive learning engine routes (Supabase/PostgreSQL edition).

All sqlite3 ? placeholders replaced with %s.
All conn.execute() calls replaced with cursor pattern.
File uploads redirected to Supabase Storage.
CURRENT_TIMESTAMP replaced with NOW().
"""
from collections import defaultdict
import os

from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from werkzeug.utils import secure_filename

from routes.guards import role_required
from database import get_db, release_db
from services.mastery_engine import (
    calculate_percentage, calculate_mastery, mastery_status,
    mastery_level, evidence_based_mastery,
)
from services.recommendation_engine import build_recommendation
from services.evidence_engine import (
    has_reflection, latest_reflection, evidence_checklist, record_ai_explanation,
)
from services.ai_explainability_engine import build_ai_explanation
from services.bkt_engine import update_bkt_record, bkt_summary

learning_bp = Blueprint("learning", __name__)

PRACTICE_CONCEPT_THRESHOLD = 70
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_latest_attempt(conn, learner_id, assessment_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM assessment_attempts
        WHERE learner_id = %s AND assessment_id = %s
        ORDER BY attempted_at DESC, attempt_id DESC LIMIT 1
    """, (learner_id, assessment_id))
    row = cur.fetchone()
    cur.close()
    return row


def get_assessment(conn, lesson_id, assessment_type):
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM assessments
        WHERE lesson_id = %s AND assessment_type = %s LIMIT 1
    """, (lesson_id, assessment_type))
    row = cur.fetchone()
    cur.close()
    return row


def is_outcome_unlocked(conn, learner_id, outcome):
    if outcome["sequence_order"] == 1:
        return True
    cur = conn.cursor()
    cur.execute("""
        SELECT prev.outcome_id
        FROM learning_outcomes current
        JOIN learning_outcomes prev
            ON prev.competency_id  = current.competency_id
           AND prev.sequence_order = current.sequence_order - 1
        WHERE current.outcome_id = %s
    """, (outcome["outcome_id"],))
    previous = cur.fetchone()
    if not previous:
        cur.close()
        return True
    cur.execute("""
        SELECT mastery_status FROM mastery_records
        WHERE learner_id = %s AND outcome_id = %s
    """, (learner_id, previous["outcome_id"]))
    prev_mastery = cur.fetchone()
    cur.close()
    return bool(prev_mastery and prev_mastery["mastery_status"] == "Mastered")


def get_required_concepts(conn, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT concept_tag FROM adaptive_notes
        WHERE outcome_id = %s ORDER BY priority, concept_tag
    """, (outcome_id,))
    rows = cur.fetchall()
    cur.close()
    return [r["concept_tag"] for r in rows]


def get_concept_mastery(conn, learner_id, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT concept_tag, latest_score, latest_assessment_type, attempt_count, concept_status
        FROM concept_mastery
        WHERE learner_id = %s AND outcome_id = %s ORDER BY concept_tag
    """, (learner_id, outcome_id))
    rows = cur.fetchall()
    cur.close()
    return {r["concept_tag"]: r for r in rows}


def get_latest_weak_concepts(conn, learner_id, outcome_id, pretest_attempt, required_concepts):
    concept_map = get_concept_mastery(conn, learner_id, outcome_id)
    practice_weak = [
        c for c in required_concepts
        if c in concept_map
        and concept_map[c]["latest_assessment_type"] == "practice"
        and concept_map[c]["latest_score"] < PRACTICE_CONCEPT_THRESHOLD
    ]
    if practice_weak:
        return practice_weak
    never_practiced = [
        c for c in required_concepts
        if c not in concept_map or concept_map[c]["latest_assessment_type"] != "practice"
    ]
    if never_practiced and pretest_attempt:
        if pretest_attempt["weak_concepts"]:
            pre_weak = [c.strip() for c in pretest_attempt["weak_concepts"].split(",") if c.strip()]
            return pre_weak or never_practiced
        return never_practiced
    return required_concepts


def get_pretest_weak_concepts(conn, learner_id, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT a.assessment_id FROM assessments a
        JOIN lessons l ON a.lesson_id = l.lesson_id
        WHERE l.outcome_id = %s AND a.assessment_type = 'pretest' LIMIT 1
    """, (outcome_id,))
    pretest = cur.fetchone()
    cur.close()
    if not pretest:
        return None, ["pretest_not_available"]
    attempt = get_latest_attempt(conn, learner_id, pretest["assessment_id"])
    if not attempt:
        return None, ["pretest_required"]
    weak = [c.strip() for c in (attempt["weak_concepts"] or "").split(",") if c.strip()]
    return attempt, weak


def posttest_unlock_status(conn, learner_id, outcome_id, required_concepts):
    pretest_attempt, weak_concepts = get_pretest_weak_concepts(conn, learner_id, outcome_id)
    if pretest_attempt is None:
        return False, weak_concepts

    cur = conn.cursor()
    cur.execute("""
        SELECT a.assessment_id FROM assessments a
        JOIN lessons l ON a.lesson_id = l.lesson_id
        WHERE l.outcome_id = %s AND a.assessment_type = 'practice' LIMIT 1
    """, (outcome_id,))
    practice = cur.fetchone()
    cur.close()

    if not practice:
        return False, ["practice_not_available"]
    practice_attempt = get_latest_attempt(conn, learner_id, practice["assessment_id"])
    if not practice_attempt:
        return False, ["practice_required"]

    if not weak_concepts:
        if practice_attempt["score"] < PRACTICE_CONCEPT_THRESHOLD:
            return False, ["practice_required"]
        if not has_reflection(conn, learner_id, outcome_id):
            return False, ["reflection_required"]
        return True, []

    concept_map = get_concept_mastery(conn, learner_id, outcome_id)
    not_ready = []
    for concept in weak_concepts:
        row = concept_map.get(concept)
        if not row:
            not_ready.append(concept)
            continue
        if row["latest_assessment_type"] in ("practice", "posttest") and row["latest_score"] >= PRACTICE_CONCEPT_THRESHOLD:
            continue
        not_ready.append(concept)

    if len(not_ready) == 0 and not has_reflection(conn, learner_id, outcome_id):
        return False, ["reflection_required"]
    return len(not_ready) == 0, not_ready


def weak_concepts_resolved(conn, learner_id, outcome_id):
    unlocked, not_ready = posttest_unlock_status(
        conn, learner_id, outcome_id, get_required_concepts(conn, outcome_id)
    )
    return unlocked and not not_ready


def latest_practical_evidence(conn, learner_id, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM practical_evidence
        WHERE learner_id = %s AND outcome_id = %s
        ORDER BY created_at DESC LIMIT 1
    """, (learner_id, outcome_id))
    row = cur.fetchone()
    cur.close()
    return row


def practical_evidence_done(conn, learner_id, outcome_id):
    return bool(latest_practical_evidence(conn, learner_id, outcome_id))


def prepare_question_items(conn, assessment_id, concept_tags=None, limit=6, learner_id=None):
    cur = conn.cursor()
    params = [assessment_id]
    concept_filter = ""
    if concept_tags:
        placeholders = ",".join(["%s"] * len(concept_tags))
        concept_filter = f" AND q.concept_tag IN ({placeholders})"
        params.extend(concept_tags)

    exclude_filter = ""
    if learner_id:
        exclude_filter = """
            AND q.question_id NOT IN (
                SELECT aa.question_id
                FROM attempt_answers aa
                JOIN assessment_attempts at ON aa.attempt_id = at.attempt_id
                WHERE at.learner_id = %s AND at.assessment_id = %s
            )
        """
        params.extend([learner_id, assessment_id])

    cur.execute(f"""
        SELECT q.question_id, q.question_text, q.concept_tag, q.marks
        FROM questions q
        WHERE q.assessment_id = %s {concept_filter} {exclude_filter}
        ORDER BY RANDOM() LIMIT %s
    """, (*params, limit))
    questions = cur.fetchall()

    if not questions:
        params2 = [assessment_id]
        cf2 = ""
        if concept_tags:
            placeholders = ",".join(["%s"] * len(concept_tags))
            cf2 = f" AND concept_tag IN ({placeholders})"
            params2.extend(concept_tags)
        cur.execute(f"""
            SELECT question_id, question_text, concept_tag, marks
            FROM questions WHERE assessment_id = %s {cf2}
            ORDER BY RANDOM() LIMIT %s
        """, (*params2, limit))
        questions = cur.fetchall()

    question_items = []
    for q in questions:
        cur.execute("""
            SELECT option_id, option_text FROM question_options
            WHERE question_id = %s ORDER BY RANDOM()
        """, (q["question_id"],))
        options = cur.fetchall()
        question_items.append({"question": q, "options": options})

    cur.close()
    return question_items


def update_concept_mastery(conn, learner_id, outcome_id, assessment_type, concept_stats):
    cur = conn.cursor()
    for concept, stats in concept_stats.items():
        score = calculate_percentage(stats["correct"], stats["total"])
        if assessment_type == "pretest":
            status = "Diagnostic Strong" if score >= PRACTICE_CONCEPT_THRESHOLD else "Diagnostic Weak"
        elif assessment_type == "practice":
            status = "Concept Mastered" if score >= PRACTICE_CONCEPT_THRESHOLD else "More Practice Needed"
        elif assessment_type == "posttest":
            status = "Post-test Strong" if score >= PRACTICE_CONCEPT_THRESHOLD else "Post-test Weak"
        else:
            status = "Attempted"

        cur.execute("""
            INSERT INTO concept_mastery
                (learner_id, outcome_id, concept_tag, latest_score, latest_assessment_type, attempt_count, concept_status)
            VALUES (%s, %s, %s, %s, %s, 1, %s)
            ON CONFLICT (learner_id, outcome_id, concept_tag)
            DO UPDATE SET
                latest_score           = EXCLUDED.latest_score,
                latest_assessment_type = EXCLUDED.latest_assessment_type,
                attempt_count          = concept_mastery.attempt_count + 1,
                concept_status         = EXCLUDED.concept_status,
                updated_at             = NOW()
        """, (learner_id, outcome_id, concept, score, assessment_type, status))
    cur.close()


# ── Route: learning pathway ───────────────────────────────────────────────────

@learning_bp.route("/pathway/<int:course_id>")
@role_required("student")
def pathway(course_id):
    learner_id = session["user_id"]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT courses.*, subjects.subject_name
            FROM courses
            JOIN subjects ON courses.subject_id = subjects.subject_id
            WHERE courses.course_id = %s
        """, (course_id,))
        course = cur.fetchone()
        if not course:
            cur.close()
            return "Pathway not found", 404

        cur.execute("""
            SELECT DISTINCT ON (lo.sequence_order)
                lo.outcome_id, lo.outcome_code, lo.outcome_name, lo.outcome_description,
                lo.mastery_threshold, lo.sequence_order,
                lessons.lesson_id, lessons.lesson_title,
                COALESCE(mr.mastery_score,  0)             AS mastery_score,
                COALESCE(mr.mastery_status, 'Not Started') AS mastery_status,
                COALESCE(mr.pretest_score,  0)             AS pretest_score,
                COALESCE(mr.practice_score, 0)             AS practice_score,
                COALESCE(mr.posttest_score, 0)             AS posttest_score
            FROM learning_outcomes lo
            JOIN lessons ON lessons.outcome_id = lo.outcome_id
            LEFT JOIN mastery_records mr
                ON mr.outcome_id = lo.outcome_id AND mr.learner_id = %s
            WHERE lessons.course_id = %s
            ORDER BY lo.sequence_order
        """, (learner_id, course_id))
        outcomes = cur.fetchall()
        cur.close()

        cards = [{"outcome": o, "unlocked": is_outcome_unlocked(conn, learner_id, o)} for o in outcomes]
    finally:
        release_db(conn)

    return render_template("learning/pathway.html", course=course, cards=cards)


# ── Route: outcome detail ─────────────────────────────────────────────────────

@learning_bp.route("/outcome/<int:outcome_id>")
@role_required("student")
def outcome(outcome_id):
    learner_id = session["user_id"]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                lo.*, c.course_id, c.course_title, s.subject_name,
                lessons.lesson_id, lessons.lesson_title, lessons.lesson_content,
                lessons.estimated_minutes,
                COALESCE(mr.pretest_score,  0)             AS pretest_score,
                COALESCE(mr.practice_score, 0)             AS practice_score,
                COALESCE(mr.posttest_score, 0)             AS posttest_score,
                COALESCE(mr.improvement_score, 0)          AS improvement_score,
                COALESCE(mr.mastery_score,  0)             AS mastery_score,
                COALESCE(mr.mastery_status, 'Not Started') AS mastery_status,
                COALESCE(mr.mastery_level,  'Beginning')   AS mastery_level
            FROM learning_outcomes lo
            JOIN lessons ON lessons.outcome_id = lo.outcome_id
            JOIN courses c ON lessons.course_id = c.course_id
            JOIN subjects s ON c.subject_id = s.subject_id
            LEFT JOIN mastery_records mr
                ON mr.outcome_id = lo.outcome_id AND mr.learner_id = %s
            WHERE lo.outcome_id = %s
            ORDER BY lessons.sequence_order
            LIMIT 1
        """, (learner_id, outcome_id))
        outcome_row = cur.fetchone()
        cur.close()

        if not outcome_row:
            return "Outcome not found", 404

        if not is_outcome_unlocked(conn, learner_id, outcome_row):
            flash("This learning outcome is locked. Master the previous outcome first.", "warning")
            return redirect(url_for("learning.pathway", course_id=outcome_row["course_id"]))

        pretest  = get_assessment(conn, outcome_row["lesson_id"], "pretest")
        practice = get_assessment(conn, outcome_row["lesson_id"], "practice")
        posttest = get_assessment(conn, outcome_row["lesson_id"], "posttest")

        pretest_attempt  = get_latest_attempt(conn, learner_id, pretest["assessment_id"])  if pretest  else None
        practice_attempt = get_latest_attempt(conn, learner_id, practice["assessment_id"]) if practice else None
        posttest_attempt = get_latest_attempt(conn, learner_id, posttest["assessment_id"]) if posttest else None

        required_concepts = get_required_concepts(conn, outcome_id)
        concept_map       = get_concept_mastery(conn, learner_id, outcome_id)
        posttest_unlocked, concepts_not_ready = posttest_unlock_status(conn, learner_id, outcome_id, required_concepts)
        weak_concepts = get_latest_weak_concepts(conn, learner_id, outcome_id, pretest_attempt, required_concepts)

        cur = conn.cursor()
        if weak_concepts:
            ph = ",".join(["%s"] * len(weak_concepts))
            cur.execute(f"""
                SELECT * FROM adaptive_notes
                WHERE outcome_id = %s AND concept_tag IN ({ph})
                ORDER BY priority, concept_tag
            """, (outcome_id, *weak_concepts))
            notes = cur.fetchall()
            cur.execute(f"""
                SELECT * FROM adaptive_videos
                WHERE outcome_id = %s AND concept_tag IN ({ph})
                ORDER BY concept_tag
            """, (outcome_id, *weak_concepts))
            videos = cur.fetchall()
            cur.execute(f"""
                SELECT * FROM worked_examples
                WHERE outcome_id = %s AND concept_tag IN ({ph})
                ORDER BY concept_tag, example_id
            """, (outcome_id, *weak_concepts))
            worked_examples = cur.fetchall()
        else:
            notes = []
            videos = []
            cur.execute("""
                SELECT * FROM worked_examples
                WHERE outcome_id = %s ORDER BY concept_tag, example_id LIMIT 4
            """, (outcome_id,))
            worked_examples = cur.fetchall()

        cur.execute("""
            SELECT * FROM learning_activities WHERE outcome_id = %s ORDER BY activity_id
        """, (outcome_id,))
        activities = cur.fetchall()

        cur.execute("""
            SELECT recommendation_reason, recommendation_type, teacher_status, created_at
            FROM recommendations
            WHERE learner_id = %s AND outcome_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (learner_id, outcome_id))
        latest_recommendation = cur.fetchone()
        cur.close()

        practical_evidence = latest_practical_evidence(conn, learner_id, outcome_id)
        bkt_rows = bkt_summary(conn, learner_id, outcome_id)
        reflection = latest_reflection(conn, learner_id, outcome_id)

        evidence = evidence_checklist(
            pretest_attempt, practice_attempt, posttest_attempt,
            posttest_unlocked, bool(reflection),
            outcome_row["posttest_score"], outcome_row["mastery_threshold"],
        )

        pretest_items  = prepare_question_items(conn, pretest["assessment_id"],  limit=6, learner_id=learner_id) if pretest else []
        practice_items = []
        if practice and pretest_attempt and not posttest_unlocked:
            practice_items = prepare_question_items(conn, practice["assessment_id"], concept_tags=weak_concepts, limit=6, learner_id=learner_id)
        elif practice and pretest_attempt:
            practice_items = prepare_question_items(conn, practice["assessment_id"], limit=6, learner_id=learner_id)
        posttest_items = prepare_question_items(conn, posttest["assessment_id"], limit=8, learner_id=learner_id) if posttest and posttest_unlocked else []

        if not pretest_attempt:
            stage = "pretest"
        elif not posttest_unlocked:
            stage = "adaptive_practice"
        elif not posttest_attempt:
            stage = "posttest"
        elif outcome_row["mastery_status"] != "Mastered":
            stage = "remediation"
        else:
            stage = "mastered"

    finally:
        release_db(conn)

    return render_template(
        "learning/outcome.html",
        outcome=outcome_row,
        pretest=pretest, practice=practice, posttest=posttest,
        pretest_attempt=pretest_attempt, practice_attempt=practice_attempt, posttest_attempt=posttest_attempt,
        pretest_items=pretest_items, practice_items=practice_items, posttest_items=posttest_items,
        notes=notes, videos=videos, activities=activities,
        weak_concepts=weak_concepts, required_concepts=required_concepts,
        concept_map=concept_map, posttest_unlocked=posttest_unlocked,
        concepts_not_ready=concepts_not_ready,
        latest_recommendation=latest_recommendation,
        reflection=reflection, practical_evidence=practical_evidence,
        worked_examples=worked_examples, bkt_rows=bkt_rows,
        evidence=evidence, stage=stage,
        practice_threshold=PRACTICE_CONCEPT_THRESHOLD,
    )


# ── Route: submit reflection ──────────────────────────────────────────────────

@learning_bp.route("/outcome/<int:outcome_id>/reflection", methods=["POST"])
@role_required("student")
def submit_reflection(outcome_id):
    learner_id       = session["user_id"]
    reflection_text  = (request.form.get("reflection_text") or "").strip()
    confidence_level = int(request.form.get("confidence_level") or 3)

    if not reflection_text:
        flash("Please write a short reflection before continuing to post-test.", "warning")
        return redirect(url_for("learning.outcome", outcome_id=outcome_id))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO learning_reflections (learner_id, outcome_id, reflection_text, confidence_level)
            VALUES (%s, %s, %s, %s)
        """, (learner_id, outcome_id, reflection_text, confidence_level))
        cur.execute("""
            INSERT INTO activity_logs (learner_id, activity_type, activity_description)
            VALUES (%s, %s, %s)
        """, (learner_id, "Reflection Submitted", f"Reflection added for outcome {outcome_id}."))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash("Reflection saved. If your practice evidence is complete, the post-test will now unlock.", "success")
    return redirect(url_for("learning.outcome", outcome_id=outcome_id))


# ── Route: submit practical evidence ─────────────────────────────────────────

@learning_bp.route("/outcome/<int:outcome_id>/practical-evidence", methods=["POST"])
@role_required("student")
def submit_practical_evidence(outcome_id):
    learner_id  = session["user_id"]
    title       = (request.form.get("evidence_title") or "Practical Evidence").strip()
    description = (request.form.get("evidence_description") or "").strip()
    file        = request.files.get("evidence_file")
    file_url    = None

    if file and file.filename:
        if not _allowed_file(file.filename):
            flash("File type not allowed. Upload PDF, PNG, JPG, JPEG or DOCX.", "danger")
            return redirect(url_for("learning.outcome", outcome_id=outcome_id))

        file.seek(0, 2)
        if file.tell() > MAX_FILE_SIZE:
            flash("File size exceeds the 5 MB limit.", "danger")
            return redirect(url_for("learning.outcome", outcome_id=outcome_id))
        file.seek(0)

        # ── Supabase Storage upload ───────────────────────────────────────────
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

        if supabase_url and supabase_key:
            from supabase import create_client
            sb = create_client(supabase_url, supabase_key)
            safe_name = secure_filename(file.filename)
            storage_path = f"learner_{learner_id}/outcome_{outcome_id}/{safe_name}"

            # Upload with correct supabase-py v2 file_options parameter
            sb.storage.from_("practical-evidence").upload(
                path=storage_path,
                file=file.read(),
                file_options={"content-type": file.content_type or "application/octet-stream"},
            )

            # Bucket is private — store the storage path, not a public URL.
            # Generate signed URLs on-demand when teachers/learners view the file.
            file_url = f"supabase://practical-evidence/{storage_path}"
        else:
            # Fallback: local filesystem (development only)
            upload_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "uploads", "practical_evidence"
            )
            os.makedirs(upload_dir, exist_ok=True)
            safe_name = secure_filename(f"learner_{learner_id}_outcome_{outcome_id}_{file.filename}")
            file.save(os.path.join(upload_dir, safe_name))
            file_url = os.path.join("uploads", "practical_evidence", safe_name)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO practical_evidence
                (learner_id, outcome_id, evidence_title, evidence_description, file_path)
            VALUES (%s, %s, %s, %s, %s)
        """, (learner_id, outcome_id, title, description, file_url))
        cur.execute("""
            INSERT INTO evidence_portfolio
                (learner_id, outcome_id, evidence_type, evidence_status, evidence_note)
            VALUES (%s, %s, 'Practical Evidence', 'Submitted', %s)
        """, (learner_id, outcome_id, description or title))
        cur.execute("""
            INSERT INTO activity_logs (learner_id, activity_type, activity_description)
            VALUES (%s, %s, %s)
        """, (learner_id, "Practical Evidence Submitted", f"Practical evidence added for outcome {outcome_id}."))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash("Practical evidence submitted for teacher review.", "success")
    return redirect(url_for("learning.outcome", outcome_id=outcome_id))


# ── Route: submit assessment ──────────────────────────────────────────────────

@learning_bp.route("/assessment/<int:assessment_id>/submit", methods=["POST"])
@role_required("student")
def submit_assessment(assessment_id):
    learner_id = session["user_id"]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT assessments.*, lessons.outcome_id, lessons.lesson_id,
                   lo.outcome_name, lo.mastery_threshold
            FROM assessments
            JOIN lessons ON assessments.lesson_id = lessons.lesson_id
            JOIN learning_outcomes lo ON lessons.outcome_id = lo.outcome_id
            WHERE assessments.assessment_id = %s
        """, (assessment_id,))
        assessment = cur.fetchone()

        if not assessment:
            cur.close()
            return "Assessment not found", 404

        required_concepts = get_required_concepts(conn, assessment["outcome_id"])
        if assessment["assessment_type"] == "posttest":
            unlocked, not_ready = posttest_unlock_status(conn, learner_id, assessment["outcome_id"], required_concepts)
            if not unlocked:
                flash("Post-test is locked. First master: " + ", ".join(not_ready), "warning")
                return redirect(url_for("learning.outcome", outcome_id=assessment["outcome_id"]))

        cur.execute("""
            SELECT question_id, question_text, concept_tag, marks
            FROM questions WHERE assessment_id = %s ORDER BY question_id
        """, (assessment_id,))
        questions = cur.fetchall()

        correct_count    = 0
        weak_concepts    = []
        answered_questions = []
        concept_stats    = defaultdict(lambda: {"correct": 0, "total": 0})

        # Insert attempt shell, retrieve new ID via RETURNING
        cur.execute("""
            INSERT INTO assessment_attempts (learner_id, assessment_id, score, weak_concepts)
            VALUES (%s, %s, 0, '') RETURNING attempt_id
        """, (learner_id, assessment_id))
        attempt_id = cur.fetchone()["attempt_id"]

        for q in questions:
            selected = request.form.get(f"question_{q['question_id']}")
            if selected is None:
                continue
            selected_option_id = int(selected)
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
                INSERT INTO attempt_answers (attempt_id, question_id, selected_option_id, is_correct)
                VALUES (%s, %s, %s, %s)
            """, (attempt_id, q["question_id"], selected_option_id, is_correct))
            update_bkt_record(conn, learner_id, assessment["outcome_id"], q["concept_tag"], is_correct)

        weak_concepts = sorted(set(weak_concepts))
        score = calculate_percentage(correct_count, len(answered_questions))
        cur.execute(
            "UPDATE assessment_attempts SET score = %s, weak_concepts = %s WHERE attempt_id = %s",
            (score, ",".join(weak_concepts), attempt_id)
        )

        update_concept_mastery(conn, learner_id, assessment["outcome_id"], assessment["assessment_type"], concept_stats)

        # Retrieve or initialise mastery record values
        cur.execute("""
            SELECT * FROM mastery_records WHERE learner_id = %s AND outcome_id = %s
        """, (learner_id, assessment["outcome_id"]))
        existing = cur.fetchone()
        pre      = existing["pretest_score"]  if existing else 0
        practice = existing["practice_score"] if existing else 0
        post     = existing["posttest_score"] if existing else 0
        mastery_score = existing["mastery_score"]  if existing else 0
        improvement   = existing["improvement_score"] if existing else 0
        status = existing["mastery_status"] if existing else "In Progress"
        level  = existing["mastery_level"]  if existing else "Beginning"

        atype = assessment["assessment_type"]
        if atype == "pretest":
            pre    = score
            status = "Adaptive Practice Required"
            level  = mastery_level(score)
        elif atype == "practice":
            practice = score
            unlocked, not_ready = posttest_unlock_status(conn, learner_id, assessment["outcome_id"], required_concepts)
            status = "Ready for Post-test" if unlocked else "Concept Practice Required"
            level  = mastery_level(score)
            weak_concepts = not_ready
        elif atype == "posttest":
            post = score
            pretest_attempt_for_evidence, _ = get_pretest_weak_concepts(conn, learner_id, assessment["outcome_id"])
            mastery_result = evidence_based_mastery(
                pretest_done=pretest_attempt_for_evidence is not None,
                activity_done=has_reflection(conn, learner_id, assessment["outcome_id"]),
                practice_score=practice,
                weak_concepts_resolved=weak_concepts_resolved(conn, learner_id, assessment["outcome_id"]),
                posttest_score=post,
                teacher_verified=False,
                threshold=assessment["mastery_threshold"],
            )
            mastery_score = mastery_result["ai_confidence"]
            improvement   = 0
            status = mastery_result["mastery_status"]
            level  = mastery_result["mastery_level"]

        cur.execute("""
            INSERT INTO mastery_records
                (learner_id, outcome_id, pretest_score, practice_score, posttest_score,
                 improvement_score, mastery_score, mastery_level, mastery_status, is_unlocked)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (learner_id, outcome_id)
            DO UPDATE SET
                pretest_score    = EXCLUDED.pretest_score,
                practice_score   = EXCLUDED.practice_score,
                posttest_score   = EXCLUDED.posttest_score,
                improvement_score = EXCLUDED.improvement_score,
                mastery_score    = EXCLUDED.mastery_score,
                mastery_level    = EXCLUDED.mastery_level,
                mastery_status   = EXCLUDED.mastery_status,
                is_unlocked      = TRUE,
                updated_at       = NOW()
        """, (learner_id, assessment["outcome_id"], pre, practice, post,
              improvement, mastery_score, level, status))

        rec = build_recommendation(
            assessment["outcome_name"], atype, score, weak_concepts,
            mastery_score if atype == "posttest" else None,
        )
        if atype == "practice" and weak_concepts:
            rec["reason"] += " Next practice focuses on: " + ", ".join(weak_concepts) + "."

        cur.execute("""
            INSERT INTO recommendations
                (learner_id, lesson_id, outcome_id, recommendation_reason, recommendation_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (learner_id, assessment["lesson_id"], assessment["outcome_id"],
              rec["reason"], rec["type"]))

        current_evidence = {
            "pretest_completed":          pre > 0 or atype == "pretest",
            "adaptive_practice_completed": practice >= PRACTICE_CONCEPT_THRESHOLD,
            "reflection_completed":        has_reflection(conn, learner_id, assessment["outcome_id"]),
            "weak_concepts_resolved":      weak_concepts_resolved(conn, learner_id, assessment["outcome_id"]),
            "posttest_passed":             post >= assessment["mastery_threshold"],
        }
        ai_exp = build_ai_explanation(
            assessment["outcome_name"], atype, score, weak_concepts,
            current_evidence, status,
        )
        record_ai_explanation(
            conn, learner_id, assessment["outcome_id"],
            ai_exp["decision"], ai_exp["evidence_used"], ai_exp["explanation"],
            mastery_score if atype == "posttest" else score,
        )

        cur.execute("""
            INSERT INTO activity_logs (learner_id, activity_type, activity_description)
            VALUES (%s, %s, %s)
        """, (learner_id, f"{atype.title()} Submitted", f"Score {score}%. Status: {status}."))

        # Unlock next outcome when mastered
        if atype == "posttest" and status == "Mastered":
            cur.execute("""
                SELECT next.outcome_id
                FROM learning_outcomes current
                JOIN learning_outcomes next
                    ON next.competency_id  = current.competency_id
                   AND next.sequence_order = current.sequence_order + 1
                WHERE current.outcome_id = %s
            """, (assessment["outcome_id"],))
            next_outcome = cur.fetchone()
            if next_outcome:
                cur.execute("""
                    INSERT INTO mastery_records
                        (learner_id, outcome_id, mastery_score, mastery_level, mastery_status, is_unlocked)
                    VALUES (%s, %s, 0, 'Beginning', 'Not Started', TRUE)
                    ON CONFLICT (learner_id, outcome_id)
                    DO UPDATE SET is_unlocked = TRUE, updated_at = NOW()
                """, (learner_id, next_outcome["outcome_id"]))

        conn.commit()
        cur.close()

    finally:
        release_db(conn)

    if atype == "pretest":
        flash(f"Pre-test submitted: {score}%. Adaptive learning has selected weak concept practice.", "success")
    elif atype == "practice":
        if status == "Ready for Post-test":
            flash(f"Practice submitted: {score}%. All concepts reached {PRACTICE_CONCEPT_THRESHOLD}%+. Post-test unlocked.", "success")
        else:
            flash(f"Practice submitted: {score}%. Next questions target weak concepts: {', '.join(weak_concepts)}.", "warning")
    else:
        flash(f"Post-test submitted: {score}%. Algorithm mastery: {mastery_score}%. Status: {status}.", "success")

    return redirect(url_for("learning.outcome", outcome_id=assessment["outcome_id"]))

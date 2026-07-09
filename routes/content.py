"""
routes/content.py — Teacher Content Management for Learn2Master.

All routes use @role_required("teacher", "admin") except admin curriculum
routes which use @role_required("admin").

Ownership model: content items (outcomes, lessons, questions, notes, videos,
examples) store a created_by FK referencing the teacher who created them.
  - Teachers see and can edit/delete ONLY their own items.
  - Admins see ALL items and can edit/delete anything.
This is enforced via _owns_item() checks and ownership-filtered queries.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
)
import psycopg2
import psycopg2.errors

from routes.guards import role_required
from database import get_db, release_db

content_bp = Blueprint("content", __name__)


# ── Ownership helpers ─────────────────────────────────────────────────────────

def _is_admin():
    return session.get("role") == "admin"


def _owner_filter_sql(alias="lo"):
    """Return a SQL WHERE fragment and params that scope results to the
    current teacher, or nothing for admins (who see everything)."""
    if _is_admin():
        return "", ()
    return f"AND {alias}.created_by = %s", (session["user_id"],)


def _assert_owns(cur, table, pk_col, pk_val):
    """Abort 403 if the current teacher doesn't own this row.
    Admins always pass. Returns the row on success."""
    if _is_admin():
        cur.execute(f"SELECT * FROM {table} WHERE {pk_col} = %s", (pk_val,))
        row = cur.fetchone()
        if not row:
            abort(404)
        return row
    cur.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = %s AND created_by = %s",
        (pk_val, session["user_id"])
    )
    row = cur.fetchone()
    if not row:
        abort(403)
    return row


# ── Helper: competency dropdown query ────────────────────────────────────────

def _fetch_competencies(cur):
    """Return competency rows suitable for a create/edit form dropdown."""
    cur.execute("""
        SELECT c.competency_id, c.competency_name, s.subject_name
        FROM competencies c
        JOIN subjects s ON c.subject_id = s.subject_id
        ORDER BY s.subject_name, c.competency_name
    """)
    return cur.fetchall()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Learning Outcomes CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@content_bp.route("/teacher/content/outcomes")
@role_required("teacher", "admin")
def list_outcomes():
    """GET — display outcomes. Teachers see only their own; admins see all."""
    conn = get_db()
    try:
        cur = conn.cursor()
        extra_sql, extra_params = _owner_filter_sql("lo")
        cur.execute(f"""
            SELECT lo.outcome_id,
                   lo.outcome_code,
                   lo.outcome_name,
                   lo.outcome_description,
                   lo.mastery_threshold,
                   lo.sequence_order,
                   lo.created_by,
                   c.competency_id,
                   c.competency_name,
                   c.competency_code,
                   s.subject_name
            FROM learning_outcomes lo
            JOIN competencies c ON lo.competency_id = c.competency_id
            JOIN subjects     s ON c.subject_id     = s.subject_id
            WHERE TRUE {extra_sql}
            ORDER BY s.subject_name, lo.sequence_order
        """, extra_params)
        outcomes = cur.fetchall()
        competencies = _fetch_competencies(cur)
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/outcomes.html",
        outcomes=outcomes,
        competencies=competencies,
    )


@content_bp.route("/teacher/content/outcomes/create", methods=["POST"])
@role_required("teacher", "admin")
def create_outcome():
    """POST — insert a new learning outcome row."""
    competency_id       = request.form.get("competency_id", "").strip()
    outcome_code        = request.form.get("outcome_code", "").strip()
    outcome_name        = request.form.get("outcome_name", "").strip()
    outcome_description = request.form.get("outcome_description", "").strip()
    mastery_threshold   = request.form.get("mastery_threshold", "").strip()
    sequence_order      = request.form.get("sequence_order", "").strip()

    # Validate required fields
    if not all([competency_id, outcome_code, outcome_name,
                outcome_description, mastery_threshold, sequence_order]):
        flash("All fields are required to create a learning outcome.", "danger")
        return redirect(url_for("content.list_outcomes"))

    # Coerce numeric fields
    try:
        mastery_threshold = int(mastery_threshold)
        sequence_order    = int(sequence_order)
        competency_id     = int(competency_id)
    except ValueError:
        flash("Mastery threshold, sequence order, and competency must be valid numbers.", "danger")
        return redirect(url_for("content.list_outcomes"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO learning_outcomes
                (competency_id, outcome_code, outcome_name,
                 outcome_description, mastery_threshold, sequence_order,
                 created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            competency_id,
            outcome_code,
            outcome_name,
            outcome_description,
            mastery_threshold,
            sequence_order,
            session["user_id"],
        ))
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash("An outcome with that code already exists for this competency.", "danger")
        return redirect(url_for("content.list_outcomes"))
    except Exception:
        conn.rollback()
        flash("Failed to create learning outcome. Please try again.", "danger")
        return redirect(url_for("content.list_outcomes"))
    finally:
        release_db(conn)

    flash("Learning outcome created successfully.", "success")
    return redirect(url_for("content.list_outcomes"))


@content_bp.route("/teacher/content/outcomes/<int:outcome_id>/edit", methods=["GET", "POST"])
@role_required("teacher", "admin")
def edit_outcome(outcome_id):
    """GET — render edit form; POST — update learning outcome row."""
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            _assert_owns(cur, "learning_outcomes", "outcome_id", outcome_id)
            cur.execute("""
                SELECT lo.outcome_id,
                       lo.outcome_code,
                       lo.outcome_name,
                       lo.outcome_description,
                       lo.mastery_threshold,
                       lo.sequence_order,
                       lo.competency_id,
                       c.competency_name,
                       s.subject_name
                FROM learning_outcomes lo
                JOIN competencies c ON lo.competency_id = c.competency_id
                JOIN subjects     s ON c.subject_id     = s.subject_id
                WHERE lo.outcome_id = %s
            """, (outcome_id,))
            outcome = cur.fetchone()
            if not outcome:
                cur.close()
                abort(404)

            competencies = _fetch_competencies(cur)
            cur.close()
        finally:
            release_db(conn)

        return render_template(
            "content/outcome_edit.html",
            outcome=outcome,
            competencies=competencies,
        )

    # POST — apply update
    competency_id       = request.form.get("competency_id", "").strip()
    outcome_code        = request.form.get("outcome_code", "").strip()
    outcome_name        = request.form.get("outcome_name", "").strip()
    outcome_description = request.form.get("outcome_description", "").strip()
    mastery_threshold   = request.form.get("mastery_threshold", "").strip()
    sequence_order      = request.form.get("sequence_order", "").strip()

    if not all([competency_id, outcome_code, outcome_name,
                outcome_description, mastery_threshold, sequence_order]):
        flash("All fields are required to update the learning outcome.", "danger")
        return redirect(url_for("content.edit_outcome", outcome_id=outcome_id))

    try:
        mastery_threshold = int(mastery_threshold)
        sequence_order    = int(sequence_order)
        competency_id     = int(competency_id)
    except ValueError:
        flash("Mastery threshold, sequence order, and competency must be valid numbers.", "danger")
        return redirect(url_for("content.edit_outcome", outcome_id=outcome_id))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE learning_outcomes
            SET competency_id       = %s,
                outcome_code        = %s,
                outcome_name        = %s,
                outcome_description = %s,
                mastery_threshold   = %s,
                sequence_order      = %s
            WHERE outcome_id = %s
        """, (
            competency_id,
            outcome_code,
            outcome_name,
            outcome_description,
            mastery_threshold,
            sequence_order,
            outcome_id,
        ))
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash("An outcome with that code already exists for this competency.", "danger")
        return redirect(url_for("content.edit_outcome", outcome_id=outcome_id))
    except Exception:
        conn.rollback()
        flash("Failed to update learning outcome. Please try again.", "danger")
        return redirect(url_for("content.edit_outcome", outcome_id=outcome_id))
    finally:
        release_db(conn)

    flash("Learning outcome updated successfully.", "success")
    return redirect(url_for("content.list_outcomes"))


@content_bp.route("/teacher/content/outcomes/<int:outcome_id>/delete", methods=["POST"])
@role_required("teacher", "admin")
def delete_outcome(outcome_id):
    """POST — safe-delete: reject if mastery_records reference this outcome."""
    conn = get_db()
    try:
        cur = conn.cursor()
        _assert_owns(cur, "learning_outcomes", "outcome_id", outcome_id)

        # Safe-delete guard: check for referencing mastery records
        cur.execute(
            "SELECT mastery_id FROM mastery_records WHERE outcome_id = %s LIMIT 1",
            (outcome_id,)
        )
        if cur.fetchone():
            cur.close()
            flash(
                "Cannot delete: learners have mastery records for this outcome.",
                "danger",
            )
            return redirect(url_for("content.list_outcomes"))

        cur.execute(
            "DELETE FROM learning_outcomes WHERE outcome_id = %s",
            (outcome_id,)
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete learning outcome. Please try again.", "danger")
        return redirect(url_for("content.list_outcomes"))
    finally:
        release_db(conn)

    flash("Learning outcome deleted successfully.", "success")
    return redirect(url_for("content.list_outcomes"))


# ── Search: outcomes + questions ──────────────────────────────────────────────

@content_bp.route("/teacher/content/search")
@role_required("teacher", "admin")
def search_content():
    """GET /teacher/content/search?q=<term>&type=outcomes|questions|notes

    Returns filtered rows as partial HTML (htmx-friendly) or full page.
    Falls back to listing all items when q is blank.
    """
    q         = request.args.get("q", "").strip()
    item_type = request.args.get("type", "outcomes")
    term      = f"%{q}%"

    conn = get_db()
    results = []
    try:
        cur = conn.cursor()
        extra_sql, extra_params = _owner_filter_sql("lo")

        if item_type == "outcomes":
            cur.execute(f"""
                SELECT lo.outcome_id, lo.outcome_code, lo.outcome_name,
                       lo.mastery_threshold, lo.sequence_order,
                       c.competency_name, s.subject_name
                FROM learning_outcomes lo
                JOIN competencies c ON lo.competency_id = c.competency_id
                JOIN subjects     s ON c.subject_id     = s.subject_id
                WHERE (lo.outcome_code ILIKE %s OR lo.outcome_name ILIKE %s
                       OR lo.outcome_description ILIKE %s)
                      {extra_sql}
                ORDER BY s.subject_name, lo.sequence_order
                LIMIT 100
            """, (term, term, term, *extra_params))
            results = cur.fetchall()

        elif item_type == "questions":
            q_extra_sql, q_extra_params = _owner_filter_sql("q") if not _is_admin() else ("", ())
            # For questions, created_by is on the questions table itself
            if not _is_admin():
                q_extra_sql   = "AND q.created_by = %s"
                q_extra_params = (session["user_id"],)
            cur.execute(f"""
                SELECT q.question_id, q.question_text, q.concept_tag,
                       q.difficulty_level, q.marks,
                       a.assessment_title, a.assessment_type,
                       l.lesson_title
                FROM questions q
                JOIN assessments a ON q.assessment_id = a.assessment_id
                JOIN lessons     l ON a.lesson_id     = l.lesson_id
                WHERE (q.question_text ILIKE %s OR q.concept_tag ILIKE %s)
                      {q_extra_sql}
                ORDER BY l.lesson_title, q.concept_tag
                LIMIT 100
            """, (term, term, *q_extra_params))
            results = cur.fetchall()

        elif item_type == "notes":
            n_extra_sql, n_extra_params = ("", ()) if _is_admin() else (
                "AND an.created_by = %s", (session["user_id"],)
            )
            cur.execute(f"""
                SELECT an.note_id, an.note_title, an.concept_tag,
                       an.priority, lo.outcome_code, lo.outcome_name
                FROM adaptive_notes an
                JOIN learning_outcomes lo ON an.outcome_id = lo.outcome_id
                WHERE (an.note_title ILIKE %s OR an.concept_tag ILIKE %s
                       OR an.note_body ILIKE %s)
                      {n_extra_sql}
                ORDER BY lo.outcome_code, an.priority
                LIMIT 100
            """, (term, term, term, *n_extra_params))
            results = cur.fetchall()

        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/search_results.html",
        results=results,
        q=q,
        item_type=item_type,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Lessons CRUD
# ═══════════════════════════════════════════════════════════════════════════════

# ── Helper: dropdown queries for lesson forms ─────────────────────────────────

def _fetch_courses(cur):
    """Return course rows for a create/edit form dropdown."""
    cur.execute("""
        SELECT course_id, course_title
        FROM courses
        ORDER BY course_title
    """)
    return cur.fetchall()


def _fetch_outcomes(cur):
    """Return learning outcome rows for a create/edit form dropdown."""
    cur.execute("""
        SELECT outcome_id, outcome_code, outcome_name
        FROM learning_outcomes
        ORDER BY outcome_code
    """)
    return cur.fetchall()


@content_bp.route("/teacher/content/lessons")
@role_required("teacher", "admin")
def list_lessons():
    """GET — display all lessons with course and outcome context."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT l.lesson_id,
                   l.lesson_title,
                   l.lesson_content,
                   l.video_url,
                   l.estimated_minutes,
                   l.sequence_order,
                   c.course_id,
                   c.course_title,
                   lo.outcome_id,
                   lo.outcome_code,
                   lo.outcome_name
            FROM lessons l
            JOIN courses           c  ON l.course_id  = c.course_id
            JOIN learning_outcomes lo ON l.outcome_id = lo.outcome_id
            ORDER BY c.course_title, l.sequence_order
        """)
        lessons = cur.fetchall()

        # Dropdown data for the inline create form
        courses  = _fetch_courses(cur)
        outcomes = _fetch_outcomes(cur)
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/lessons.html",
        lessons=lessons,
        courses=courses,
        outcomes=outcomes,
    )


@content_bp.route("/teacher/content/lessons/create", methods=["POST"])
@role_required("teacher", "admin")
def create_lesson():
    """POST — insert a new lesson row."""
    course_id         = request.form.get("course_id", "").strip()
    outcome_id        = request.form.get("outcome_id", "").strip()
    lesson_title      = request.form.get("lesson_title", "").strip()
    lesson_content    = request.form.get("lesson_content", "").strip() or None
    video_url         = request.form.get("video_url", "").strip() or None
    estimated_minutes = request.form.get("estimated_minutes", "").strip()
    sequence_order    = request.form.get("sequence_order", "").strip()

    # Required fields
    if not all([course_id, outcome_id, lesson_title, sequence_order]):
        flash("Course, outcome, lesson title, and sequence order are required.", "danger")
        return redirect(url_for("content.list_lessons"))

    try:
        course_id         = int(course_id)
        outcome_id        = int(outcome_id)
        sequence_order    = int(sequence_order)
        estimated_minutes = int(estimated_minutes) if estimated_minutes else None
    except ValueError:
        flash("Course, outcome, sequence order, and estimated minutes must be valid numbers.", "danger")
        return redirect(url_for("content.list_lessons"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO lessons
                (course_id, outcome_id, lesson_title, lesson_content,
                 video_url, estimated_minutes, sequence_order, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            course_id,
            outcome_id,
            lesson_title,
            lesson_content,
            video_url,
            estimated_minutes,
            sequence_order,
            session["user_id"],
        ))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to create lesson. Please try again.", "danger")
        return redirect(url_for("content.list_lessons"))
    finally:
        release_db(conn)

    flash("Lesson created successfully.", "success")
    return redirect(url_for("content.list_lessons"))


@content_bp.route("/teacher/content/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
@role_required("teacher", "admin")
def edit_lesson(lesson_id):
    """GET — render edit form; POST — update lesson row."""
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT lesson_id,
                       course_id,
                       outcome_id,
                       lesson_title,
                       lesson_content,
                       video_url,
                       estimated_minutes,
                       sequence_order
                FROM lessons
                WHERE lesson_id = %s
            """, (lesson_id,))
            lesson = cur.fetchone()
            if not lesson:
                cur.close()
                abort(404)

            courses  = _fetch_courses(cur)
            outcomes = _fetch_outcomes(cur)
            cur.close()
        finally:
            release_db(conn)

        return render_template(
            "content/lesson_edit.html",
            lesson=lesson,
            courses=courses,
            outcomes=outcomes,
        )

    # POST — apply update
    course_id         = request.form.get("course_id", "").strip()
    outcome_id        = request.form.get("outcome_id", "").strip()
    lesson_title      = request.form.get("lesson_title", "").strip()
    lesson_content    = request.form.get("lesson_content", "").strip() or None
    video_url         = request.form.get("video_url", "").strip() or None
    estimated_minutes = request.form.get("estimated_minutes", "").strip()
    sequence_order    = request.form.get("sequence_order", "").strip()

    if not all([course_id, outcome_id, lesson_title, sequence_order]):
        flash("Course, outcome, lesson title, and sequence order are required.", "danger")
        return redirect(url_for("content.edit_lesson", lesson_id=lesson_id))

    try:
        course_id         = int(course_id)
        outcome_id        = int(outcome_id)
        sequence_order    = int(sequence_order)
        estimated_minutes = int(estimated_minutes) if estimated_minutes else None
    except ValueError:
        flash("Course, outcome, sequence order, and estimated minutes must be valid numbers.", "danger")
        return redirect(url_for("content.edit_lesson", lesson_id=lesson_id))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE lessons
            SET course_id         = %s,
                outcome_id        = %s,
                lesson_title      = %s,
                lesson_content    = %s,
                video_url         = %s,
                estimated_minutes = %s,
                sequence_order    = %s
            WHERE lesson_id = %s
        """, (
            course_id,
            outcome_id,
            lesson_title,
            lesson_content,
            video_url,
            estimated_minutes,
            sequence_order,
            lesson_id,
        ))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to update lesson. Please try again.", "danger")
        return redirect(url_for("content.edit_lesson", lesson_id=lesson_id))
    finally:
        release_db(conn)

    flash("Lesson updated successfully.", "success")
    return redirect(url_for("content.list_lessons"))


@content_bp.route("/teacher/content/lessons/<int:lesson_id>/delete", methods=["POST"])
@role_required("teacher", "admin")
def delete_lesson(lesson_id):
    """POST — safe-delete: reject if assessments reference this lesson."""
    conn = get_db()
    try:
        cur = conn.cursor()

        # Safe-delete guard: check for referencing assessments
        cur.execute(
            "SELECT assessment_id FROM assessments WHERE lesson_id = %s LIMIT 1",
            (lesson_id,)
        )
        if cur.fetchone():
            cur.close()
            flash(
                "Cannot delete: assessments are linked to this lesson. "
                "Remove the assessments first.",
                "danger",
            )
            return redirect(url_for("content.list_lessons"))

        cur.execute("DELETE FROM lessons WHERE lesson_id = %s", (lesson_id,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete lesson. Please try again.", "danger")
        return redirect(url_for("content.list_lessons"))
    finally:
        release_db(conn)

    flash("Lesson deleted successfully.", "success")
    return redirect(url_for("content.list_lessons"))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Questions CRUD
# ═══════════════════════════════════════════════════════════════════════════════

# ── Helper: assessment dropdown query ────────────────────────────────────────

def _fetch_assessments(cur):
    """Return assessment rows (with lesson context) for a form dropdown."""
    cur.execute("""
        SELECT a.assessment_id,
               a.assessment_title,
               a.assessment_type,
               l.lesson_title
        FROM assessments a
        JOIN lessons l ON a.lesson_id = l.lesson_id
        ORDER BY l.lesson_title, a.assessment_type
    """)
    return cur.fetchall()


@content_bp.route("/teacher/content/questions")
@role_required("teacher", "admin")
def list_questions():
    """GET — display all questions with assessment/lesson context."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT q.question_id,
                   q.question_text,
                   q.concept_tag,
                   q.difficulty_level,
                   q.question_type,
                   q.marks,
                   a.assessment_id,
                   a.assessment_title,
                   a.assessment_type,
                   l.lesson_title
            FROM questions q
            JOIN assessments a ON q.assessment_id = a.assessment_id
            JOIN lessons     l ON a.lesson_id     = l.lesson_id
            ORDER BY l.lesson_title, a.assessment_type, q.question_id
        """)
        questions = cur.fetchall()

        # Dropdown data for the inline create form
        assessments = _fetch_assessments(cur)
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/questions.html",
        questions=questions,
        assessments=assessments,
    )


@content_bp.route("/teacher/content/questions/create", methods=["POST"])
@role_required("teacher", "admin")
def create_question():
    """POST — insert a question row plus one option row per submitted option.

    Form fields:
      assessment_id, question_text, concept_tag, difficulty_level,
      question_type, marks, option_text[] (list), correct_option_index (radio)
    Validation: 2–6 options; correct_option_index must be in range.
    All inserts run in a single transaction.
    """
    assessment_id        = request.form.get("assessment_id", "").strip()
    question_text        = request.form.get("question_text", "").strip()
    concept_tag          = request.form.get("concept_tag", "").strip()
    difficulty_level     = request.form.get("difficulty_level", "standard").strip()
    question_type        = request.form.get("question_type", "multiple_choice").strip()
    marks                = request.form.get("marks", "1").strip()
    option_texts         = request.form.getlist("option_text")
    correct_index_raw    = request.form.get("correct_option_index", "").strip()

    # Strip blank option entries that the JS may have left
    option_texts = [o.strip() for o in option_texts if o.strip()]

    # Required field validation
    if not all([assessment_id, question_text, concept_tag]):
        flash("Assessment, question text, and concept tag are required.", "danger")
        return redirect(url_for("content.list_questions"))

    # Option count validation
    if len(option_texts) < 2 or len(option_texts) > 6:
        flash("A question must have between 2 and 6 answer options.", "danger")
        return redirect(url_for("content.list_questions"))

    # Correct-index validation
    try:
        correct_index = int(correct_index_raw)
        if correct_index < 0 or correct_index >= len(option_texts):
            raise ValueError
    except (ValueError, TypeError):
        flash("Please select exactly one correct answer option.", "danger")
        return redirect(url_for("content.list_questions"))

    # Numeric coercions
    try:
        assessment_id = int(assessment_id)
        marks         = int(marks) if marks else 1
    except ValueError:
        flash("Assessment and marks must be valid numbers.", "danger")
        return redirect(url_for("content.list_questions"))

    conn = get_db()
    try:
        cur = conn.cursor()

        # Insert the question row and capture the new question_id
        cur.execute("""
            INSERT INTO questions
                (assessment_id, question_text, concept_tag,
                 difficulty_level, question_type, marks)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING question_id
        """, (
            assessment_id,
            question_text,
            concept_tag,
            difficulty_level,
            question_type,
            marks,
        ))
        new_question_id = cur.fetchone()["question_id"]

        # Insert one option row per submitted option
        for idx, text in enumerate(option_texts):
            cur.execute("""
                INSERT INTO question_options (question_id, option_text, is_correct)
                VALUES (%s, %s, %s)
            """, (new_question_id, text, idx == correct_index))

        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to create question. Please try again.", "danger")
        return redirect(url_for("content.list_questions"))
    finally:
        release_db(conn)

    flash("Question created successfully.", "success")
    return redirect(url_for("content.list_questions"))


@content_bp.route(
    "/teacher/content/questions/<int:question_id>/edit",
    methods=["GET", "POST"],
)
@role_required("teacher", "admin")
def edit_question(question_id):
    """GET — render edit form with existing question + options.
    POST — UPDATE question row, DELETE old options, INSERT fresh option set.
    All writes occur in a single transaction.
    """
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()

            # Fetch the question row
            cur.execute("""
                SELECT q.question_id,
                       q.assessment_id,
                       q.question_text,
                       q.concept_tag,
                       q.difficulty_level,
                       q.question_type,
                       q.marks,
                       a.assessment_title,
                       a.assessment_type,
                       l.lesson_title
                FROM questions q
                JOIN assessments a ON q.assessment_id = a.assessment_id
                JOIN lessons     l ON a.lesson_id     = l.lesson_id
                WHERE q.question_id = %s
            """, (question_id,))
            question = cur.fetchone()
            if not question:
                cur.close()
                abort(404)

            # Fetch all existing options for this question
            cur.execute("""
                SELECT option_id, option_text, is_correct
                FROM question_options
                WHERE question_id = %s
                ORDER BY option_id
            """, (question_id,))
            options = cur.fetchall()

            # Determine current correct index (0-based)
            correct_index = next(
                (i for i, o in enumerate(options) if o["is_correct"]),
                0,
            )

            assessments = _fetch_assessments(cur)
            cur.close()
        finally:
            release_db(conn)

        return render_template(
            "content/question_edit.html",
            question=question,
            options=options,
            correct_index=correct_index,
            assessments=assessments,
        )

    # ── POST — apply update ───────────────────────────────────────────────────
    assessment_id     = request.form.get("assessment_id", "").strip()
    question_text     = request.form.get("question_text", "").strip()
    concept_tag       = request.form.get("concept_tag", "").strip()
    difficulty_level  = request.form.get("difficulty_level", "standard").strip()
    question_type     = request.form.get("question_type", "multiple_choice").strip()
    marks             = request.form.get("marks", "1").strip()
    option_texts      = request.form.getlist("option_text")
    correct_index_raw = request.form.get("correct_option_index", "").strip()

    # Strip blanks
    option_texts = [o.strip() for o in option_texts if o.strip()]

    if not all([assessment_id, question_text, concept_tag]):
        flash("Assessment, question text, and concept tag are required.", "danger")
        return redirect(url_for("content.edit_question", question_id=question_id))

    if len(option_texts) < 2 or len(option_texts) > 6:
        flash("A question must have between 2 and 6 answer options.", "danger")
        return redirect(url_for("content.edit_question", question_id=question_id))

    try:
        correct_index = int(correct_index_raw)
        if correct_index < 0 or correct_index >= len(option_texts):
            raise ValueError
    except (ValueError, TypeError):
        flash("Please select exactly one correct answer option.", "danger")
        return redirect(url_for("content.edit_question", question_id=question_id))

    try:
        assessment_id = int(assessment_id)
        marks         = int(marks) if marks else 1
    except ValueError:
        flash("Assessment and marks must be valid numbers.", "danger")
        return redirect(url_for("content.edit_question", question_id=question_id))

    conn = get_db()
    try:
        cur = conn.cursor()

        # Update the question row
        cur.execute("""
            UPDATE questions
            SET assessment_id    = %s,
                question_text    = %s,
                concept_tag      = %s,
                difficulty_level = %s,
                question_type    = %s,
                marks            = %s
            WHERE question_id = %s
        """, (
            assessment_id,
            question_text,
            concept_tag,
            difficulty_level,
            question_type,
            marks,
            question_id,
        ))

        # Delete all existing options for this question
        cur.execute(
            "DELETE FROM question_options WHERE question_id = %s",
            (question_id,)
        )

        # Insert fresh option set
        for idx, text in enumerate(option_texts):
            cur.execute("""
                INSERT INTO question_options (question_id, option_text, is_correct)
                VALUES (%s, %s, %s)
            """, (question_id, text, idx == correct_index))

        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to update question. Please try again.", "danger")
        return redirect(url_for("content.edit_question", question_id=question_id))
    finally:
        release_db(conn)

    flash("Question updated successfully.", "success")
    return redirect(url_for("content.list_questions"))


@content_bp.route(
    "/teacher/content/questions/<int:question_id>/delete",
    methods=["POST"],
)
@role_required("teacher", "admin")
def delete_question(question_id):
    """POST — DELETE question_options then questions in a single transaction."""
    conn = get_db()
    try:
        cur = conn.cursor()

        # Delete child options first (FK constraint)
        cur.execute(
            "DELETE FROM question_options WHERE question_id = %s",
            (question_id,)
        )
        # Delete the question itself
        cur.execute(
            "DELETE FROM questions WHERE question_id = %s",
            (question_id,)
        )

        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete question. Please try again.", "danger")
        return redirect(url_for("content.list_questions"))
    finally:
        release_db(conn)

    flash("Question deleted successfully.", "success")
    return redirect(url_for("content.list_questions"))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Adaptive Notes CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@content_bp.route("/teacher/content/notes")
@role_required("teacher", "admin")
def list_notes():
    """GET — display all adaptive notes joined to learning outcomes."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT an.note_id,
                   an.concept_tag,
                   an.note_title,
                   an.note_body,
                   an.priority,
                   lo.outcome_id,
                   lo.outcome_code,
                   lo.outcome_name
            FROM adaptive_notes an
            JOIN learning_outcomes lo ON an.outcome_id = lo.outcome_id
            ORDER BY lo.outcome_code, an.priority, an.note_title
        """)
        notes = cur.fetchall()

        # Dropdown data for the inline create form
        outcomes = _fetch_outcomes(cur)
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/notes.html",
        notes=notes,
        outcomes=outcomes,
    )


@content_bp.route("/teacher/content/notes/create", methods=["POST"])
@role_required("teacher", "admin")
def create_note():
    """POST — INSERT a new adaptive_notes row."""
    outcome_id  = request.form.get("outcome_id", "").strip()
    concept_tag = request.form.get("concept_tag", "").strip()
    note_title  = request.form.get("note_title", "").strip()
    note_body   = request.form.get("note_body", "").strip()
    priority    = request.form.get("priority", "").strip()

    # All fields required
    if not all([outcome_id, concept_tag, note_title, note_body, priority]):
        flash("All fields are required to create an adaptive note.", "danger")
        return redirect(url_for("content.list_notes"))

    # Coerce and validate numeric fields
    try:
        outcome_id = int(outcome_id)
        priority   = int(priority)
        if priority < 1:
            raise ValueError
    except ValueError:
        flash("Outcome must be selected and priority must be a positive integer.", "danger")
        return redirect(url_for("content.list_notes"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO adaptive_notes
                (outcome_id, concept_tag, note_title, note_body, priority)
            VALUES (%s, %s, %s, %s, %s)
        """, (outcome_id, concept_tag, note_title, note_body, priority))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to create adaptive note. Please try again.", "danger")
        return redirect(url_for("content.list_notes"))
    finally:
        release_db(conn)

    flash("Adaptive note created successfully.", "success")
    return redirect(url_for("content.list_notes"))


@content_bp.route(
    "/teacher/content/notes/<int:note_id>/edit",
    methods=["GET", "POST"],
)
@role_required("teacher", "admin")
def edit_note(note_id):
    """GET — render edit form; POST — UPDATE adaptive_notes row."""
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT an.note_id,
                       an.outcome_id,
                       an.concept_tag,
                       an.note_title,
                       an.note_body,
                       an.priority,
                       lo.outcome_code,
                       lo.outcome_name
                FROM adaptive_notes an
                JOIN learning_outcomes lo ON an.outcome_id = lo.outcome_id
                WHERE an.note_id = %s
            """, (note_id,))
            note = cur.fetchone()
            if not note:
                cur.close()
                abort(404)

            outcomes = _fetch_outcomes(cur)
            cur.close()
        finally:
            release_db(conn)

        return render_template(
            "content/note_edit.html",
            note=note,
            outcomes=outcomes,
        )

    # POST — apply update
    outcome_id  = request.form.get("outcome_id", "").strip()
    concept_tag = request.form.get("concept_tag", "").strip()
    note_title  = request.form.get("note_title", "").strip()
    note_body   = request.form.get("note_body", "").strip()
    priority    = request.form.get("priority", "").strip()

    if not all([outcome_id, concept_tag, note_title, note_body, priority]):
        flash("All fields are required to update the adaptive note.", "danger")
        return redirect(url_for("content.edit_note", note_id=note_id))

    try:
        outcome_id = int(outcome_id)
        priority   = int(priority)
        if priority < 1:
            raise ValueError
    except ValueError:
        flash("Outcome must be selected and priority must be a positive integer.", "danger")
        return redirect(url_for("content.edit_note", note_id=note_id))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE adaptive_notes
            SET outcome_id  = %s,
                concept_tag = %s,
                note_title  = %s,
                note_body   = %s,
                priority    = %s
            WHERE note_id = %s
        """, (outcome_id, concept_tag, note_title, note_body, priority, note_id))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to update adaptive note. Please try again.", "danger")
        return redirect(url_for("content.edit_note", note_id=note_id))
    finally:
        release_db(conn)

    flash("Adaptive note updated successfully.", "success")
    return redirect(url_for("content.list_notes"))


@content_bp.route(
    "/teacher/content/notes/<int:note_id>/delete",
    methods=["POST"],
)
@role_required("teacher", "admin")
def delete_note(note_id):
    """POST — DELETE adaptive_notes row (no FK downstream dependency)."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM adaptive_notes WHERE note_id = %s", (note_id,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete adaptive note. Please try again.", "danger")
        return redirect(url_for("content.list_notes"))
    finally:
        release_db(conn)

    flash("Adaptive note deleted successfully.", "success")
    return redirect(url_for("content.list_notes"))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Adaptive Videos & Worked Examples CRUD
# ═══════════════════════════════════════════════════════════════════════════════

# ── Adaptive Videos ──────────────────────────────────────────────────────────

@content_bp.route("/teacher/content/videos")
@role_required("teacher", "admin")
def list_videos():
    """GET — display all adaptive videos joined to learning outcomes."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT av.video_id,
                   av.concept_tag,
                   av.video_title,
                   av.video_url,
                   av.video_description,
                   lo.outcome_id,
                   lo.outcome_code,
                   lo.outcome_name
            FROM adaptive_videos av
            JOIN learning_outcomes lo ON av.outcome_id = lo.outcome_id
            ORDER BY lo.outcome_code, av.video_title
        """)
        videos = cur.fetchall()

        # Dropdown data for the inline create form
        outcomes = _fetch_outcomes(cur)
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/videos.html",
        videos=videos,
        outcomes=outcomes,
    )


@content_bp.route("/teacher/content/videos/create", methods=["POST"])
@role_required("teacher", "admin")
def create_video():
    """POST — INSERT a new adaptive_videos row."""
    outcome_id        = request.form.get("outcome_id", "").strip()
    concept_tag       = request.form.get("concept_tag", "").strip()
    video_title       = request.form.get("video_title", "").strip()
    video_url         = request.form.get("video_url", "").strip()
    video_description = request.form.get("video_description", "").strip() or None

    # Required field validation
    if not all([outcome_id, concept_tag, video_title, video_url]):
        flash("Outcome, concept tag, video title, and video URL are required.", "danger")
        return redirect(url_for("content.list_videos"))

    try:
        outcome_id = int(outcome_id)
    except ValueError:
        flash("A valid learning outcome must be selected.", "danger")
        return redirect(url_for("content.list_videos"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO adaptive_videos
                (outcome_id, concept_tag, video_title, video_url, video_description)
            VALUES (%s, %s, %s, %s, %s)
        """, (outcome_id, concept_tag, video_title, video_url, video_description))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to create adaptive video. Please try again.", "danger")
        return redirect(url_for("content.list_videos"))
    finally:
        release_db(conn)

    flash("Adaptive video created successfully.", "success")
    return redirect(url_for("content.list_videos"))


@content_bp.route(
    "/teacher/content/videos/<int:video_id>/delete",
    methods=["POST"],
)
@role_required("teacher", "admin")
def delete_video(video_id):
    """POST — DELETE adaptive_videos row (no FK downstream dependency)."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM adaptive_videos WHERE video_id = %s", (video_id,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete adaptive video. Please try again.", "danger")
        return redirect(url_for("content.list_videos"))
    finally:
        release_db(conn)

    flash("Adaptive video deleted successfully.", "success")
    return redirect(url_for("content.list_videos"))


# ── Worked Examples ───────────────────────────────────────────────────────────

@content_bp.route("/teacher/content/examples")
@role_required("teacher", "admin")
def list_examples():
    """GET — display all worked examples joined to learning outcomes."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT we.example_id,
                   we.concept_tag,
                   we.example_title,
                   we.example_body,
                   we.step_by_step_solution,
                   lo.outcome_id,
                   lo.outcome_code,
                   lo.outcome_name
            FROM worked_examples we
            JOIN learning_outcomes lo ON we.outcome_id = lo.outcome_id
            ORDER BY lo.outcome_code, we.example_title
        """)
        examples = cur.fetchall()

        # Dropdown data for the inline create form
        outcomes = _fetch_outcomes(cur)
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/examples.html",
        examples=examples,
        outcomes=outcomes,
    )


@content_bp.route("/teacher/content/examples/create", methods=["POST"])
@role_required("teacher", "admin")
def create_example():
    """POST — INSERT a new worked_examples row."""
    outcome_id            = request.form.get("outcome_id", "").strip()
    concept_tag           = request.form.get("concept_tag", "").strip()
    example_title         = request.form.get("example_title", "").strip()
    example_body          = request.form.get("example_body", "").strip()
    step_by_step_solution = request.form.get("step_by_step_solution", "").strip() or None

    # Required field validation
    if not all([outcome_id, concept_tag, example_title, example_body]):
        flash("Outcome, concept tag, example title, and example body are required.", "danger")
        return redirect(url_for("content.list_examples"))

    try:
        outcome_id = int(outcome_id)
    except ValueError:
        flash("A valid learning outcome must be selected.", "danger")
        return redirect(url_for("content.list_examples"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO worked_examples
                (outcome_id, concept_tag, example_title, example_body, step_by_step_solution)
            VALUES (%s, %s, %s, %s, %s)
        """, (outcome_id, concept_tag, example_title, example_body, step_by_step_solution))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to create worked example. Please try again.", "danger")
        return redirect(url_for("content.list_examples"))
    finally:
        release_db(conn)

    flash("Worked example created successfully.", "success")
    return redirect(url_for("content.list_examples"))


@content_bp.route(
    "/teacher/content/examples/<int:example_id>/delete",
    methods=["POST"],
)
@role_required("teacher", "admin")
def delete_example(example_id):
    """POST — DELETE worked_examples row (no FK downstream dependency)."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM worked_examples WHERE example_id = %s", (example_id,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete worked example. Please try again.", "danger")
        return redirect(url_for("content.list_examples"))
    finally:
        release_db(conn)

    flash("Worked example deleted successfully.", "success")
    return redirect(url_for("content.list_examples"))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Admin Curriculum Routes  (Task 7 — to be added)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Admin Curriculum Routes
# Requirement refs: R1.19–R1.20
# ═══════════════════════════════════════════════════════════════════════════════

# ── Helper: fetch subjects for dropdowns ─────────────────────────────────────

def _fetch_subjects(cur):
    """Return subject rows for a create/edit form dropdown."""
    cur.execute("""
        SELECT subject_id, subject_name
        FROM subjects
        ORDER BY subject_name
    """)
    return cur.fetchall()


# ── GET /admin/content/curriculum — combined list page ───────────────────────

@content_bp.route("/admin/content/curriculum")
@role_required("admin")
def admin_curriculum():
    """GET — single page showing all subjects, competencies, and courses."""
    conn = get_db()
    try:
        cur = conn.cursor()

        cur.execute("SELECT subject_id, subject_name FROM subjects ORDER BY subject_name")
        subjects = cur.fetchall()

        cur.execute("""
            SELECT c.competency_id,
                   c.subject_id,
                   c.competency_code,
                   c.competency_name,
                   c.competency_description,
                   s.subject_name
            FROM competencies c
            JOIN subjects s ON c.subject_id = s.subject_id
            ORDER BY s.subject_name, c.competency_code
        """)
        competencies = cur.fetchall()

        cur.execute("""
            SELECT co.course_id,
                   co.subject_id,
                   co.course_title,
                   co.course_description,
                   co.difficulty_level,
                   s.subject_name
            FROM courses co
            JOIN subjects s ON co.subject_id = s.subject_id
            ORDER BY s.subject_name, co.course_title
        """)
        courses = cur.fetchall()

        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "content/admin_curriculum.html",
        subjects=subjects,
        competencies=competencies,
        courses=courses,
    )


# ── Subjects CRUD ─────────────────────────────────────────────────────────────

@content_bp.route(
    "/admin/content/subjects/create",
    methods=["GET", "POST"],
)
@role_required("admin")
def admin_create_subject():
    """GET — redirect to curriculum page; POST — INSERT into subjects."""
    if request.method == "GET":
        return redirect(url_for("content.admin_curriculum"))

    subject_name = request.form.get("subject_name", "").strip()

    if not subject_name:
        flash("Subject name is required.", "danger")
        return redirect(url_for("content.admin_curriculum"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO subjects (subject_name) VALUES (%s)",
            (subject_name,),
        )
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash("A subject with that name already exists.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    except Exception:
        conn.rollback()
        flash("Failed to create subject. Please try again.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    finally:
        release_db(conn)

    flash("Subject created successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


@content_bp.route(
    "/admin/content/subjects/<int:subject_id>/edit",
    methods=["GET", "POST"],
)
@role_required("admin")
def admin_edit_subject(subject_id):
    """GET — render edit form; POST — UPDATE subjects row."""
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT subject_id, subject_name FROM subjects WHERE subject_id = %s",
                (subject_id,),
            )
            subject = cur.fetchone()
            if not subject:
                cur.close()
                abort(404)
            cur.close()
        finally:
            release_db(conn)

        return render_template("content/admin_subject_edit.html", subject=subject)

    # POST — apply update
    subject_name = request.form.get("subject_name", "").strip()

    if not subject_name:
        flash("Subject name is required.", "danger")
        return redirect(url_for("content.admin_edit_subject", subject_id=subject_id))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE subjects SET subject_name = %s WHERE subject_id = %s",
            (subject_name, subject_id),
        )
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash("A subject with that name already exists.", "danger")
        return redirect(url_for("content.admin_edit_subject", subject_id=subject_id))
    except Exception:
        conn.rollback()
        flash("Failed to update subject. Please try again.", "danger")
        return redirect(url_for("content.admin_edit_subject", subject_id=subject_id))
    finally:
        release_db(conn)

    flash("Subject updated successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


@content_bp.route(
    "/admin/content/subjects/<int:subject_id>/delete",
    methods=["POST"],
)
@role_required("admin")
def admin_delete_subject(subject_id):
    """POST — DELETE subjects row directly (admin responsibility, no guard)."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM subjects WHERE subject_id = %s", (subject_id,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete subject. Please try again.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    finally:
        release_db(conn)

    flash("Subject deleted successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


# ── Competencies CRUD ─────────────────────────────────────────────────────────

@content_bp.route(
    "/admin/content/competencies/create",
    methods=["GET", "POST"],
)
@role_required("admin")
def admin_create_competency():
    """GET — redirect to curriculum page; POST — INSERT into competencies."""
    if request.method == "GET":
        return redirect(url_for("content.admin_curriculum"))

    subject_id             = request.form.get("subject_id", "").strip()
    competency_code        = request.form.get("competency_code", "").strip()
    competency_name        = request.form.get("competency_name", "").strip()
    competency_description = request.form.get("competency_description", "").strip() or None

    if not all([subject_id, competency_code, competency_name]):
        flash("Subject, competency code, and competency name are required.", "danger")
        return redirect(url_for("content.admin_curriculum"))

    try:
        subject_id = int(subject_id)
    except ValueError:
        flash("A valid subject must be selected.", "danger")
        return redirect(url_for("content.admin_curriculum"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO competencies
                (subject_id, competency_code, competency_name, competency_description)
            VALUES (%s, %s, %s, %s)
        """, (subject_id, competency_code, competency_name, competency_description))
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash(
            "A competency with that code already exists for the selected subject.",
            "danger",
        )
        return redirect(url_for("content.admin_curriculum"))
    except Exception:
        conn.rollback()
        flash("Failed to create competency. Please try again.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    finally:
        release_db(conn)

    flash("Competency created successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


@content_bp.route(
    "/admin/content/competencies/<int:competency_id>/edit",
    methods=["GET", "POST"],
)
@role_required("admin")
def admin_edit_competency(competency_id):
    """GET — render edit form; POST — UPDATE competencies row."""
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT competency_id,
                       subject_id,
                       competency_code,
                       competency_name,
                       competency_description
                FROM competencies
                WHERE competency_id = %s
            """, (competency_id,))
            competency = cur.fetchone()
            if not competency:
                cur.close()
                abort(404)

            subjects = _fetch_subjects(cur)
            cur.close()
        finally:
            release_db(conn)

        return render_template(
            "content/admin_competency_edit.html",
            competency=competency,
            subjects=subjects,
        )

    # POST — apply update
    subject_id             = request.form.get("subject_id", "").strip()
    competency_code        = request.form.get("competency_code", "").strip()
    competency_name        = request.form.get("competency_name", "").strip()
    competency_description = request.form.get("competency_description", "").strip() or None

    if not all([subject_id, competency_code, competency_name]):
        flash("Subject, competency code, and competency name are required.", "danger")
        return redirect(
            url_for("content.admin_edit_competency", competency_id=competency_id)
        )

    try:
        subject_id = int(subject_id)
    except ValueError:
        flash("A valid subject must be selected.", "danger")
        return redirect(
            url_for("content.admin_edit_competency", competency_id=competency_id)
        )

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE competencies
            SET subject_id             = %s,
                competency_code        = %s,
                competency_name        = %s,
                competency_description = %s
            WHERE competency_id = %s
        """, (
            subject_id,
            competency_code,
            competency_name,
            competency_description,
            competency_id,
        ))
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash(
            "A competency with that code already exists for the selected subject.",
            "danger",
        )
        return redirect(
            url_for("content.admin_edit_competency", competency_id=competency_id)
        )
    except Exception:
        conn.rollback()
        flash("Failed to update competency. Please try again.", "danger")
        return redirect(
            url_for("content.admin_edit_competency", competency_id=competency_id)
        )
    finally:
        release_db(conn)

    flash("Competency updated successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


@content_bp.route(
    "/admin/content/competencies/<int:competency_id>/delete",
    methods=["POST"],
)
@role_required("admin")
def admin_delete_competency(competency_id):
    """POST — DELETE competencies row."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM competencies WHERE competency_id = %s",
            (competency_id,),
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete competency. Please try again.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    finally:
        release_db(conn)

    flash("Competency deleted successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


# ── Courses CRUD ──────────────────────────────────────────────────────────────

@content_bp.route(
    "/admin/content/courses/create",
    methods=["GET", "POST"],
)
@role_required("admin")
def admin_create_course():
    """GET — redirect to curriculum page; POST — INSERT into courses."""
    if request.method == "GET":
        return redirect(url_for("content.admin_curriculum"))

    subject_id         = request.form.get("subject_id", "").strip()
    course_title       = request.form.get("course_title", "").strip()
    course_description = request.form.get("course_description", "").strip() or None
    difficulty_level   = request.form.get("difficulty_level", "").strip() or None

    if not all([subject_id, course_title]):
        flash("Subject and course title are required.", "danger")
        return redirect(url_for("content.admin_curriculum"))

    try:
        subject_id = int(subject_id)
    except ValueError:
        flash("A valid subject must be selected.", "danger")
        return redirect(url_for("content.admin_curriculum"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO courses
                (subject_id, course_title, course_description, difficulty_level)
            VALUES (%s, %s, %s, %s)
        """, (subject_id, course_title, course_description, difficulty_level))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to create course. Please try again.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    finally:
        release_db(conn)

    flash("Course created successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


@content_bp.route(
    "/admin/content/courses/<int:course_id>/edit",
    methods=["GET", "POST"],
)
@role_required("admin")
def admin_edit_course(course_id):
    """GET — render edit form; POST — UPDATE courses row."""
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT course_id,
                       subject_id,
                       course_title,
                       course_description,
                       difficulty_level
                FROM courses
                WHERE course_id = %s
            """, (course_id,))
            course = cur.fetchone()
            if not course:
                cur.close()
                abort(404)

            subjects = _fetch_subjects(cur)
            cur.close()
        finally:
            release_db(conn)

        return render_template(
            "content/admin_curriculum_course_edit.html",
            course=course,
            subjects=subjects,
        )

    # POST — apply update
    subject_id         = request.form.get("subject_id", "").strip()
    course_title       = request.form.get("course_title", "").strip()
    course_description = request.form.get("course_description", "").strip() or None
    difficulty_level   = request.form.get("difficulty_level", "").strip() or None

    if not all([subject_id, course_title]):
        flash("Subject and course title are required.", "danger")
        return redirect(url_for("content.admin_edit_course", course_id=course_id))

    try:
        subject_id = int(subject_id)
    except ValueError:
        flash("A valid subject must be selected.", "danger")
        return redirect(url_for("content.admin_edit_course", course_id=course_id))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE courses
            SET subject_id         = %s,
                course_title       = %s,
                course_description = %s,
                difficulty_level   = %s
            WHERE course_id = %s
        """, (
            subject_id,
            course_title,
            course_description,
            difficulty_level,
            course_id,
        ))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to update course. Please try again.", "danger")
        return redirect(url_for("content.admin_edit_course", course_id=course_id))
    finally:
        release_db(conn)

    flash("Course updated successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))


@content_bp.route(
    "/admin/content/courses/<int:course_id>/delete",
    methods=["POST"],
)
@role_required("admin")
def admin_delete_course(course_id):
    """POST — DELETE courses row."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM courses WHERE course_id = %s", (course_id,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        flash("Failed to delete course. Please try again.", "danger")
        return redirect(url_for("content.admin_curriculum"))
    finally:
        release_db(conn)

    flash("Course deleted successfully.", "success")
    return redirect(url_for("content.admin_curriculum"))

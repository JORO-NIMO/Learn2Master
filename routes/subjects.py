"""routes/subjects.py — Subject and pathway routes (Supabase/PostgreSQL edition)."""
from flask import Blueprint, render_template, session
from routes.guards import role_required
from database import get_db, release_db

subjects_bp = Blueprint("subjects", __name__)


@subjects_bp.route("/subjects")
@role_required("student")
def subjects():
    learner_id = session["user_id"]

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT subject_id, subject_name
            FROM subjects
            WHERE subject_name IN ('Physics', 'ICT')
            ORDER BY CASE subject_name WHEN 'Physics' THEN 1 WHEN 'ICT' THEN 2 ELSE 3 END
        """)
        subject_rows = cur.fetchall()

        subject_cards = []
        for subject in subject_rows:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM learning_outcomes lo
                JOIN competencies c ON lo.competency_id = c.competency_id
                WHERE c.subject_id = %s
            """, (subject["subject_id"],))
            total = cur.fetchone()["total"]

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM mastery_records mr
                JOIN learning_outcomes lo ON mr.outcome_id = lo.outcome_id
                JOIN competencies c ON lo.competency_id = c.competency_id
                WHERE c.subject_id = %s AND mr.learner_id = %s AND mr.mastery_status = 'Mastered'
            """, (subject["subject_id"], learner_id))
            mastered = cur.fetchone()["total"]

            progress = round((mastered / total) * 100) if total else 0
            name = subject["subject_name"]
            subject_cards.append({
                "id":          subject["subject_id"],
                "name":        name,
                "code":        "PHY" if name == "Physics" else "ICT",
                "icon":        "⚛" if name == "Physics" else "💻",
                "description": (
                    "Senior One research topic: Measurements in Physics."
                    if name == "Physics"
                    else "Senior One research topic: Introduction to ICT."
                ),
                "progress": progress,
                "mastered": mastered,
                "total":    total,
            })

        cur.close()
    finally:
        release_db(conn)

    return render_template("subjects.html", subjects=subject_cards)


@subjects_bp.route("/subjects/<int:subject_id>")
@role_required("student")
def subject_detail(subject_id):
    learner_id = session["user_id"]

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM subjects WHERE subject_id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            cur.close()
            return "Subject not found", 404

        cur.execute("""
            SELECT course_id, course_title, course_description, difficulty_level
            FROM courses WHERE subject_id = %s ORDER BY course_id
        """, (subject_id,))
        pathways = cur.fetchall()

        pathway_cards = []
        for p in pathways:
            cur.execute("""
                SELECT COUNT(*) AS total FROM lessons WHERE course_id = %s
            """, (p["course_id"],))
            total = cur.fetchone()["total"]

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM mastery_records mr
                JOIN lessons l ON mr.outcome_id = l.outcome_id
                WHERE l.course_id = %s AND mr.learner_id = %s AND mr.mastery_status = 'Mastered'
            """, (p["course_id"], learner_id))
            mastered = cur.fetchone()["total"]

            progress = round((mastered / total) * 100) if total else 0
            pathway_cards.append({
                "pathway":  p,
                "progress": progress,
                "mastered": mastered,
                "total":    total,
            })

        cur.close()
    finally:
        release_db(conn)

    return render_template("subject_detail.html", subject=subject, pathway_cards=pathway_cards)

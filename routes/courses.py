"""routes/courses.py — Course listing route (Supabase/PostgreSQL edition)."""
from flask import Blueprint, render_template, redirect, session, url_for
from database import get_db, release_db

courses_bp = Blueprint("courses", __name__)


@courses_bp.route("/courses")
def courses():
    if "user_id" not in session:
        return redirect(url_for("auth.home"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                courses.course_id,
                courses.course_title,
                courses.course_description,
                courses.difficulty_level,
                subjects.subject_name
            FROM courses
            JOIN subjects ON courses.subject_id = subjects.subject_id
            ORDER BY subjects.subject_name, courses.course_title
        """)
        course_list = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    return render_template("courses.html", courses=course_list)

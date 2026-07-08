"""
app.py — Learn2Master Flask application entry point.

Supabase/PostgreSQL edition.
"""
import os
from dotenv import load_dotenv
from flask import Flask, session, redirect, url_for, request
from flask_wtf.csrf import CSRFProtect

# Load .env before anything accesses os.environ
load_dotenv()

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.courses import courses_bp
from routes.mastery import mastery_bp
from routes.teacher import teacher_bp
from routes.admin import admin_bp
from routes.student import student_bp
from routes.subjects import subjects_bp
from routes.learning import learning_bp
from routes.framework import framework_bp
from routes.profile import profile_bp
from routes.analytics import analytics_bp
from routes.research import research_bp
from routes.content import content_bp
from routes.sync import sync_bp

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__)

# Secret key MUST come from the environment — never hardcoded
secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. "
        "Add it to your .env file: "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = secret_key

# CSRF protection for all POST forms
csrf = CSRFProtect(app)
app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1 hour

# ── Cache-control headers (keep session/auth pages private) ──────────────────
@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── Session version validation — detect stale sessions after role change ──────
# When an admin changes a user's role, their role_id in the DB changes.
# The next request from that user will have an outdated session["session_version"]
# (which stores the old role_id). We detect this mismatch and force re-login.
_SESSION_EXEMPT_PREFIXES = ("/static/", "/service-worker.js", "/sync")

@app.before_request
def validate_session_version():
    # Skip for unauthenticated requests, static files, and the sync endpoint
    user_id = session.get("user_id")
    if not user_id:
        return
    if any(request.path.startswith(p) for p in _SESSION_EXEMPT_PREFIXES):
        return
    # Only validate once every N seconds to avoid a DB query on every request.
    # Use Flask session to store last-checked timestamp.
    import time
    last_check = session.get("_sv_checked", 0)
    if time.time() - last_check < 120:   # re-check every 2 minutes
        return
    from database import get_db, release_db
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        release_db(conn)
    if row is None:
        # User was deleted — invalidate session
        session.clear()
        return redirect(url_for("auth.home"))
    current_role_id = row["role_id"]
    stored_version  = session.get("session_version")
    if stored_version is not None and current_role_id != stored_version:
        # Role changed — force re-login so session reflects new role
        session.clear()
        from flask import flash
        flash("Your account permissions have been updated. Please log in again.", "warning")
        return redirect(url_for("auth.home"))
    # Update timestamp and persist current version
    session["_sv_checked"]      = time.time()
    session["session_version"]  = current_role_id


# ── Context processor: inject pending AI recommendation count into all templates
# Teachers and admins see a badge on the AI Insights sidebar link.
@app.context_processor
def inject_pending_recs():
    from flask import session as _sess
    role = _sess.get("role")
    if role not in ("teacher", "admin"):
        return {}
    user_id = _sess.get("user_id")
    if not user_id:
        return {}
    try:
        from database import get_db, release_db
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM recommendations
                WHERE teacher_status = 'Pending Review'
            """)
            row = cur.fetchone()
            cur.close()
            pending_recs = int(row["cnt"]) if row else 0
        finally:
            release_db(conn)
    except Exception:
        pending_recs = 0
    return {"pending_recs_count": pending_recs}


# ── Blueprint registration ────────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(courses_bp)
app.register_blueprint(mastery_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(student_bp)
app.register_blueprint(subjects_bp)
app.register_blueprint(learning_bp)
app.register_blueprint(framework_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(research_bp)
app.register_blueprint(content_bp)
app.register_blueprint(sync_bp)
csrf.exempt(sync_bp)


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode)

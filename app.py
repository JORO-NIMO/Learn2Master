"""
app.py — Learn2Master Flask application entry point.

Supabase/PostgreSQL edition.

Registered blueprints (15):
    auth, dashboard, courses, mastery, teacher, admin, student,
    subjects, learning, framework, profile, analytics, research,
    content, sync

Application-level middleware:
    - CSRF protection (Flask-WTF) — all blueprints except sync_bp
    - Cache-control headers — prevents browser caching of private pages
    - Session version validation — forces re-login when a user's role changes
    - Pending-recs context processor — injects badge count into all templates
"""

import os
import time

from dotenv import load_dotenv
from flask import Flask, flash, redirect, request, session, url_for
from flask_wtf.csrf import CSRFProtect

# ── Environment ───────────────────────────────────────────────────────────────
# Load .env BEFORE any module that reads os.environ (including database.py)
load_dotenv()

# ── Blueprint imports ─────────────────────────────────────────────────────────
from routes.admin     import admin_bp
from routes.analytics import analytics_bp
from routes.auth      import auth_bp
from routes.content   import content_bp
from routes.courses   import courses_bp
from routes.dashboard import dashboard_bp
from routes.framework import framework_bp
from routes.learning  import learning_bp
from routes.mastery   import mastery_bp
from routes.profile   import profile_bp
from routes.research  import research_bp
from routes.student   import student_bp
from routes.subjects  import subjects_bp
from routes.sync      import sync_bp
from routes.teacher   import teacher_bp

# ── DB helpers (imported here so all middleware can use them) ─────────────────
from database import get_db, release_db

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__)

# Secret key — MUST come from the environment, never hardcoded
secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. "
        "Add it to your .env file:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = secret_key

# ── CSRF protection ───────────────────────────────────────────────────────────
csrf = CSRFProtect(app)
app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1 hour token lifetime

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

# /sync is a JSON endpoint — it validates CSRF from the JSON body itself.
# Exempting it from Flask-WTF's form-based middleware is required.
csrf.exempt(sync_bp)


# ════════════════════════════════════════════════════════════════════════════════
# Middleware
# ════════════════════════════════════════════════════════════════════════════════

# ── 1. Cache-control ──────────────────────────────────────────────────────────
@app.after_request
def add_no_cache_headers(response):
    """Prevent browsers from caching authenticated pages."""
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, private, max-age=0"
    )
    response.headers["Pragma"]  = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── 2. Session version validation ────────────────────────────────────────────
# session["session_version"] stores the user's role_id at login time.
# If an admin changes that user's role the role_id in the DB changes.
# The next authenticated request (after a 2-minute cooldown) detects the
# mismatch and forces a re-login so the session reflects the new role.
_SESSION_EXEMPT_PREFIXES = ("/static/", "/service-worker.js", "/sync")
_SESSION_CHECK_INTERVAL  = 120   # seconds between DB checks per session


@app.before_request
def validate_session_version():
    user_id = session.get("user_id")
    if not user_id:
        return  # unauthenticated — nothing to validate

    # Skip static assets and the JSON sync endpoint
    if any(request.path.startswith(p) for p in _SESSION_EXEMPT_PREFIXES):
        return

    # Rate-limit DB checks to once per interval using a session timestamp
    last_check = session.get("_sv_checked", 0)
    if time.time() - last_check < _SESSION_CHECK_INTERVAL:
        return

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        release_db(conn)

    if row is None:
        # Account was deleted — clear session and send to login
        session.clear()
        return redirect(url_for("auth.home"))

    current_role_id = row["role_id"]
    stored_version  = session.get("session_version")

    if stored_version is not None and current_role_id != stored_version:
        # Role changed — invalidate session and prompt re-login
        session.clear()
        flash(
            "Your account permissions have been updated. "
            "Please log in again.",
            "warning",
        )
        return redirect(url_for("auth.home"))

    # Refresh the stored version and the check timestamp
    session["session_version"] = current_role_id
    session["_sv_checked"]     = time.time()


# ── 3. Pending AI recommendations badge ──────────────────────────────────────
# Injects `pending_recs_count` into every Jinja2 template so the teacher
# and admin sidebars can show a red badge on the AI Insights link.
# Falls back to 0 silently on any DB error so the rest of the page still loads.
@app.context_processor
def inject_pending_recs():
    role    = session.get("role")
    user_id = session.get("user_id")

    if role not in ("teacher", "admin") or not user_id:
        return {"pending_recs_count": 0}

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM recommendations
                WHERE teacher_status = 'Pending Review'
            """)
            row = cur.fetchone()
            cur.close()
            count = int(row["cnt"]) if row else 0
        finally:
            release_db(conn)
    except Exception:
        count = 0

    return {"pending_recs_count": count}


# ════════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode)

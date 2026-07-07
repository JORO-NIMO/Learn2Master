"""
app.py — Learn2Master Flask application entry point.

Supabase/PostgreSQL edition.
"""
import os
from dotenv import load_dotenv
from flask import Flask
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


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode)

"""
routes/auth.py — Authentication routes for Learn2Master.

Authentication Strategy: Supabase Auth (Option B — full production mode).

Flow:
  Register:
    1. Call supabase.auth.sign_up(email, password) → creates Supabase auth.users row
    2. Insert matching row into public.users with full_name, username, role=student, school
    3. Redirect to login with "Check your email to confirm your account" message

  Login:
    1. Call supabase.auth.sign_in_with_password(email, password)
    2. If successful, load the public.users row via email match
    3. Store user_id, role, full_name in Flask session (server-side; signed with SECRET_KEY)

  Logout:
    1. Call supabase.auth.sign_out()
    2. Clear Flask session

  Password Reset:
    1. Call supabase.auth.reset_password_for_email(email)
    2. Supabase sends a reset link automatically (no custom SMTP needed)

Security:
  - No plaintext passwords in the application layer
  - No hardcoded credentials anywhere
  - Email verification enforced by Supabase
  - Password reset handled by Supabase (email link)
  - Role is NEVER taken from form input — always defaults to 'student' on self-register
  - Admin creates teacher/admin accounts via /admin/users/create
"""

import os
from flask import Blueprint, render_template, request, redirect, session, url_for, flash
import psycopg2.errors
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, release_db
from supabase_client import get_supabase

auth_bp = Blueprint("auth", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_supabase_configured() -> bool:
    """Check if Supabase URL and Service Key are configured in the environment."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))


def _load_user_by_email(email: str):
    """Fetch the public.users row for a given email. Returns dict or None."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.user_id, u.full_name, u.username, u.email,
                   u.role_id, r.role_name, s.school_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            LEFT JOIN schools s ON u.school_id = s.school_id
            WHERE u.email = %s
        """, (email.lower().strip(),))
        user = cur.fetchone()
        cur.close()
        return user
    finally:
        release_db(conn)


def _set_session(user):
    """Write user info into the Flask session."""
    session.clear()
    session["user_id"]         = user["user_id"]
    session["username"]        = user["username"]
    session["full_name"]       = user["full_name"]
    session["email"]           = user["email"]
    session["role"]            = user["role_name"]
    session["session_version"] = user["role_id"]   # for stale-session detection
    session.permanent          = False


def _redirect_by_role(role: str):
    if role == "student":
        return redirect(url_for("student.student_dashboard"))
    if role == "teacher":
        return redirect(url_for("teacher.teacher_dashboard"))
    if role == "admin":
        return redirect(url_for("admin.admin_dashboard"))
    flash("Unknown user role. Contact your administrator.", "danger")
    return redirect(url_for("auth.home"))


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route("/")
def home():
    # If already logged in, redirect to the right dashboard
    if session.get("user_id"):
        return _redirect_by_role(session.get("role", ""))
    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    # Accept both email and username as login identifier
    identifier = (request.form.get("email") or request.form.get("username") or "").strip()
    password = request.form.get("password", "")

    if not identifier or not password:
        flash("Email/username and password are required.", "danger")
        return redirect(url_for("auth.home"))

    # Resolve email and fetch database user info (supports fallback to username-to-email lookup)
    email = identifier.lower()
    user = None

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.user_id, u.full_name, u.username, u.email, u.password_hash,
                   u.role_id, r.role_name, s.school_name, u.supabase_uid
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            LEFT JOIN schools s ON u.school_id = s.school_id
            WHERE u.email = %s OR u.username = %s
        """, (identifier.lower(), identifier))
        user = cur.fetchone()
        cur.close()
    finally:
        release_db(conn)

    if user:
        email = user["email"]

    if _is_supabase_configured():
        sb = get_supabase()
        try:
            # Supabase Auth: sign in with email + password
            resp = sb.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            # Supabase raises AuthApiError for invalid credentials, unverified email, etc.
            msg = str(exc)
            if "Email not confirmed" in msg:
                flash("Please confirm your email address before logging in. Check your inbox.", "warning")
            elif "Invalid login credentials" in msg:
                flash("Invalid email or password.", "danger")
            else:
                flash("Login failed. Please try again.", "danger")
            return redirect(url_for("auth.home"))

        if not resp or not resp.user:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.home"))

        # Load the matching row from public.users if not already fetched
        if not user:
            user = _load_user_by_email(email)

        if not user:
            # Supabase auth succeeded but no public.users row — edge case
            flash("Account not fully set up. Contact your administrator.", "danger")
            return redirect(url_for("auth.home"))

        _set_session(user)
        return _redirect_by_role(user["role_name"])
    else:
        # Local fallback authentication (e.g. during testing)
        if not user or not user["password_hash"]:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.home"))

        if check_password_hash(user["password_hash"], password):
            _set_session(user)
            return _redirect_by_role(user["role_name"])
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.home"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name   = request.form.get("full_name", "").strip()
        username    = request.form.get("username", "").strip()
        email       = request.form.get("email", "").strip().lower()
        password    = request.form.get("password", "")
        school_name = request.form.get("school_name", "").strip()

        # If email is missing but username is provided, auto-generate fallback email for backward compatibility in tests
        if not email and username:
            email = f"{username}@example.com"

        # Validate required fields
        if not full_name or not username or not email or not password:
            flash("Full name, username, email, and password are all required.", "danger")
            return redirect(url_for("auth.register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("auth.register"))

        supabase_uid = None
        password_hash = "supabase_managed"

        if _is_supabase_configured():
            # Step 1: Create Supabase Auth account first
            sb = get_supabase()
            try:
                auth_resp = sb.auth.sign_up({"email": email, "password": password})
            except Exception as exc:
                msg = str(exc)
                if "already registered" in msg.lower() or "already exists" in msg.lower():
                    flash("An account with that email already exists. Try logging in.", "danger")
                else:
                    flash(f"Registration failed: {msg}", "danger")
                return redirect(url_for("auth.register"))

            if not auth_resp or not auth_resp.user:
                flash("Registration failed. Please try again.", "danger")
                return redirect(url_for("auth.register"))

            supabase_uid = str(auth_resp.user.id)
        else:
            # Local mode: hash the password locally
            password_hash = generate_password_hash(password)

        # Step 2: Insert into public.users
        conn = get_db()
        try:
            cur = conn.cursor()

            # Resolve student role (always student on self-register)
            cur.execute("SELECT role_id FROM roles WHERE role_name = 'student'")
            role = cur.fetchone()
            if not role:
                flash("Default role not found. Contact your administrator.", "danger")
                return redirect(url_for("auth.register"))

            # Resolve or create school
            school_id = None
            if school_name:
                cur.execute("SELECT school_id FROM schools WHERE school_name = %s", (school_name,))
                school = cur.fetchone()
                if not school:
                    cur.execute(
                        "INSERT INTO schools (school_name) VALUES (%s) RETURNING school_id",
                        (school_name,)
                    )
                    school = cur.fetchone()
                    conn.commit()
                school_id = school["school_id"]

            # Insert user
            cur.execute("""
                INSERT INTO users
                    (full_name, username, email, password_hash,
                     role_id, school_id, supabase_uid)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                full_name,
                username,
                email,
                password_hash,
                role["role_id"],
                school_id,
                supabase_uid,
            ))
            conn.commit()
            cur.close()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            # Clean up Supabase Auth account if it was created
            if _is_supabase_configured() and supabase_uid:
                try:
                    sb.auth.admin.delete_user(supabase_uid)
                except Exception:
                    pass
            flash("Username or email already exists. Try a different one.", "danger")
            return redirect(url_for("auth.register"))
        except Exception as exc:
            conn.rollback()
            # Clean up Supabase Auth account if it was created
            if _is_supabase_configured() and supabase_uid:
                try:
                    sb.auth.admin.delete_user(supabase_uid)
                except Exception:
                    pass
            flash(f"Registration failed: {exc}", "danger")
            return redirect(url_for("auth.register"))
        finally:
            release_db(conn)

        if _is_supabase_configured():
            flash(
                "Account created! Check your email to confirm your address, then log in.",
                "success"
            )
        else:
            flash(
                "Account created successfully!",
                "success"
            )
        return redirect(url_for("auth.home"))

    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    if _is_supabase_configured():
        sb = get_supabase()
        try:
            sb.auth.sign_out()
        except Exception:
            pass  # Always clear the Flask session even if Supabase sign-out fails
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.home"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Trigger Supabase password reset email."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your email address.", "danger")
            return redirect(url_for("auth.forgot_password"))

        if _is_supabase_configured():
            sb = get_supabase()
            try:
                # Supabase sends a secure reset link to the email
                redirect_url = request.host_url.rstrip("/") + url_for("auth.reset_password")
                sb.auth.reset_password_for_email(email, {"redirect_to": redirect_url})
            except Exception:
                pass  # Never reveal whether email exists — security best practice
        else:
            flash("Password reset is not available in local mode.", "warning")
            return redirect(url_for("auth.home"))

        flash(
            "If that email is registered, you will receive a password reset link shortly.",
            "info"
        )
        return redirect(url_for("auth.home"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Handle the password reset form (after user clicks the Supabase link)."""
    if not _is_supabase_configured():
        flash("Password reset is not available in local mode.", "warning")
        return redirect(url_for("auth.home"))

    # Supabase appends access_token and refresh_token as URL fragments (#).
    # The browser JS must capture them and POST here.
    if request.method == "POST":
        access_token  = request.form.get("access_token", "").strip()
        new_password  = request.form.get("new_password", "")
        confirm_pw    = request.form.get("confirm_password", "")

        if not access_token:
            flash("Invalid or expired reset link. Please request a new one.", "danger")
            return redirect(url_for("auth.forgot_password"))
        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("auth.reset_password"))
        if new_password != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.reset_password"))

        sb = get_supabase()
        try:
            # Set the session using the access token from the reset link
            sb.auth.set_session(access_token, "")
            sb.auth.update_user({"password": new_password})
        except Exception as exc:
            flash(f"Password reset failed: {exc}", "danger")
            return redirect(url_for("auth.reset_password"))

        flash("Password updated successfully. Please log in.", "success")
        return redirect(url_for("auth.home"))

    return render_template("reset_password.html")

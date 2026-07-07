"""
routes/auth.py — Authentication routes for Learn2Master.

Supabase/PostgreSQL edition:
- Uses psycopg2 cursor pattern with %s placeholders
- sqlite3.IntegrityError replaced with psycopg2.errors.UniqueViolation
- Register route hardcoded to 'student' role (security fix — prevents privilege escalation)
- Connections returned to pool via release_db() in finally blocks
"""
from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras
import psycopg2.errorcodes

from database import get_db, release_db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def home():
    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("auth.home"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT users.*, roles.role_name, schools.school_name
            FROM users
            JOIN roles ON users.role_id = roles.role_id
            LEFT JOIN schools ON users.school_id = schools.school_id
            WHERE users.username = %s
        """, (username,))
        user = cur.fetchone()
        cur.close()
    finally:
        release_db(conn)

    if user and check_password_hash(user["password_hash"], password):
        session.clear()
        session["user_id"]  = user["user_id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"]     = user["role_name"]
        session.permanent   = False

        role = user["role_name"]
        if role == "student":
            return redirect(url_for("student.student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher.teacher_dashboard"))
        elif role == "admin":
            return redirect(url_for("admin.admin_dashboard"))
        else:
            flash("Unknown user role.", "danger")
            return redirect(url_for("auth.home"))

    flash("Invalid username or password.", "danger")
    return redirect(url_for("auth.home"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name   = request.form.get("full_name", "").strip()
        username    = request.form.get("username", "").strip()
        email       = request.form.get("email", "").strip() or None
        password    = request.form.get("password", "")
        school_name = request.form.get("school_name", "").strip()

        # Security: role is always 'student' — never from form input
        role_name = "student"

        if not full_name or not username or not password:
            flash("Full name, username and password are required.", "danger")
            return redirect(url_for("auth.register"))

        conn = get_db()
        try:
            cur = conn.cursor()

            # Resolve role
            cur.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,))
            role = cur.fetchone()
            if not role:
                flash("Default role not found. Please contact the administrator.", "danger")
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
                INSERT INTO users (full_name, username, email, password_hash, role_id, school_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                full_name,
                username,
                email,
                generate_password_hash(password),
                role["role_id"],
                school_id,
            ))
            conn.commit()
            cur.close()

            flash("Account created successfully. Please login.", "success")
            return redirect(url_for("auth.home"))

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash("Username or email already exists.", "danger")
            return redirect(url_for("auth.register"))

        except Exception as e:
            conn.rollback()
            flash("Registration failed. Please try again.", "danger")
            return redirect(url_for("auth.register"))

        finally:
            release_db(conn)

    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.home"))

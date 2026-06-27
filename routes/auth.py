from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

from database import get_db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def home():
    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    conn = get_db()

    user = conn.execute("""
        SELECT users.*, roles.role_name, schools.school_name
        FROM users
        JOIN roles ON users.role_id = roles.role_id
        LEFT JOIN schools ON users.school_id = schools.school_id
        WHERE users.username = ?
    """, (username,)).fetchone()

    conn.close()

    if user and check_password_hash(user["password_hash"], password):

        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role_name"]

        if user["role_name"] == "student":
            return redirect(url_for("student.student_dashboard"))

        elif user["role_name"] == "teacher":
            return redirect(url_for("teacher.teacher_dashboard"))

        elif user["role_name"] == "admin":
            return redirect(url_for("admin.admin_dashboard"))

        else:
            flash("Unknown user role.", "danger")
            return redirect(url_for("auth.home"))

    flash("Invalid username or password.", "danger")
    return redirect(url_for("auth.home"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        school_name = request.form.get("school_name")
        role_name = request.form.get("role", "student")

        conn = get_db()

        role = conn.execute(
            "SELECT role_id FROM roles WHERE role_name = ?",
            (role_name,)
        ).fetchone()

        school = conn.execute(
            "SELECT school_id FROM schools WHERE school_name = ?",
            (school_name,)
        ).fetchone()

        if not school:
            conn.execute("INSERT INTO schools (school_name) VALUES (?)", (school_name,))
            conn.commit()
            school = conn.execute(
                "SELECT school_id FROM schools WHERE school_name = ?",
                (school_name,)
            ).fetchone()

        try:
            conn.execute("""
                INSERT INTO users
                (full_name, username, email, password_hash, role_id, school_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                full_name,
                username,
                email,
                generate_password_hash(password),
                role["role_id"],
                school["school_id"]
            ))
            conn.commit()
            flash("Account created successfully. Please login.", "success")
            return redirect(url_for("auth.home"))

        except sqlite3.IntegrityError:
            flash("Username or email already exists.", "danger")
            return redirect(url_for("auth.register"))

        finally:
            conn.close()

    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.home"))
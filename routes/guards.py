from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("auth.home"))
        return view(*args, **kwargs)
    return wrapped_view


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                flash("Please login first.", "warning")
                return redirect(url_for("auth.home"))

            if session.get("role") not in roles:
                flash("You are not allowed to access that page.", "danger")
                return redirect(url_for("dashboard.dashboard"))

            return view(*args, **kwargs)
        return wrapped_view
    return decorator
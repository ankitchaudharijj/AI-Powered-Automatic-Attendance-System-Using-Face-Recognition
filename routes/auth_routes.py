"""
routes/auth_routes.py
======================
Login/logout pages for the server-rendered admin dashboard.
"""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from controllers.auth_controller import AuthController
from utils.decorators import login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
auth_controller = AuthController()


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    """Render and process the admin login form."""
    if session.get("admin_id"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        identifier = request.form.get("username", "")
        password = request.form.get("password", "")

        success, message = auth_controller.login(identifier, password)
        if success:
            flash(message, "success")
            next_url = request.args.get("next") or url_for("dashboard.index")
            return redirect(next_url)

        flash(message, "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    """Log the current admin out and return to the login page."""
    auth_controller.logout()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Let the logged-in admin/teacher change their own password."""
    if request.method == "POST":
        success, message = auth_controller.change_password(
            current_password=request.form.get("current_password", ""),
            new_password=request.form.get("new_password", ""),
            confirm_password=request.form.get("confirm_password", ""),
        )
        flash(message, "success" if success else "danger")
        if success:
            return redirect(url_for("dashboard.index"))

    return render_template("auth/change_password.html")


@auth_bp.route("/session-ping", methods=["POST"])
def session_ping():
    """
    Lightweight AJAX endpoint hit by the "Extend Session" button and by
    normal background activity. Because SESSION_REFRESH_EACH_REQUEST is
    enabled, simply handling any authenticated request resets the
    5-minute inactivity countdown — this endpoint just gives the
    frontend a cheap, side-effect-free way to do that.
    """
    if not session.get("admin_id"):
        return jsonify(success=False, message="Session already expired."), 401
    return jsonify(success=True)

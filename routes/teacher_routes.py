"""
routes/teacher_routes.py
=========================
Superadmin-only pages for creating teacher accounts and assigning them
to one or more classes. Teachers themselves cannot access these routes.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from controllers.class_controller import ClassController
from controllers.teacher_controller import TeacherController
from utils.decorators import superadmin_required

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teachers")
teacher_controller = TeacherController()
class_controller = ClassController()


@teacher_bp.route("/")
@superadmin_required
def list_teachers():
    """List every teacher account with their assigned classes."""
    teachers = teacher_controller.list_teachers()
    classes = class_controller.list_all()
    return render_template("admin/manage_teachers.html", teachers=teachers, classes=classes)


@teacher_bp.route("/create", methods=["POST"])
@superadmin_required
def create():
    """Create a new teacher account and assign it to one or more classes."""
    _, error = teacher_controller.create_teacher(request.form)
    flash(error if error else "Teacher account created successfully.", "danger" if error else "success")
    return redirect(url_for("teacher.list_teachers"))


@teacher_bp.route("/<int:admin_id>/assign", methods=["POST"])
@superadmin_required
def assign(admin_id: int):
    """Update which classes a teacher is assigned to."""
    _, error = teacher_controller.update_assignments(admin_id, request.form)
    flash(error if error else "Class assignments updated.", "danger" if error else "success")
    return redirect(url_for("teacher.list_teachers"))


@teacher_bp.route("/<int:admin_id>/deactivate", methods=["POST"])
@superadmin_required
def deactivate(admin_id: int):
    """Deactivate a teacher account (soft-disable, does not delete history)."""
    _, error = teacher_controller.deactivate(admin_id)
    flash(error if error else "Teacher account deactivated.", "danger" if error else "info")
    return redirect(url_for("teacher.list_teachers"))


@teacher_bp.route("/<int:admin_id>/unlock", methods=["POST"])
@superadmin_required
def unlock(admin_id: int):
    """Immediately clear a login lockout for this teacher (before the 24h expires)."""
    _, error = teacher_controller.unlock(admin_id)
    flash(error if error else "Account unlocked successfully.", "danger" if error else "success")
    return redirect(url_for("teacher.list_teachers"))

"""
controllers/teacher_controller.py
==================================
HTTP-facing coordination layer for superadmin-only teacher account
management: creating teacher logins and assigning them to classes.
"""

from __future__ import annotations

from models import AdminRole
from services.auth_service import AuthService
from utils.helpers import safe_int


class TeacherController:
    """Coordinates teacher account creation, listing, and class assignment."""

    def __init__(self) -> None:
        self.auth_service = AuthService()

    def list_teachers(self):
        return self.auth_service.list_teachers()

    def create_teacher(self, form):
        class_ids = [safe_int(cid) for cid in form.getlist("class_ids")]
        class_ids = [cid for cid in class_ids if cid is not None]

        return self.auth_service.create_admin(
            username=form.get("username", ""),
            email=form.get("email", ""),
            full_name=form.get("full_name", ""),
            password=form.get("password", ""),
            role=AdminRole.TEACHER,
            class_ids=class_ids,
        )

    def update_assignments(self, admin_id: int, form):
        class_ids = [safe_int(cid) for cid in form.getlist("class_ids")]
        class_ids = [cid for cid in class_ids if cid is not None]
        return self.auth_service.assign_classes(admin_id, class_ids)

    def deactivate(self, admin_id: int):
        return self.auth_service.deactivate_admin(admin_id)

    def unlock(self, admin_id: int):
        return self.auth_service.unlock_admin(admin_id)

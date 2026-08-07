"""
controllers/auth_controller.py
===============================
Translates HTTP requests for login/logout/JWT into AuthService calls
and shapes the responses (session cookie for the dashboard, JSON+JWT
for the API).
"""

from __future__ import annotations

from flask import session

from services.auth_service import AuthService


class AuthController:
    """Coordinates login/logout flows for both session and JWT auth."""

    def __init__(self) -> None:
        self.auth_service = AuthService()

    def login(self, identifier: str, password: str) -> tuple[bool, str]:
        """
        Attempt a session-based login (used by the HTML dashboard).

        Returns:
            (success, message)
        """
        admin, error = self.auth_service.authenticate(identifier, password)
        if error:
            return False, error

        session.permanent = True
        session["admin_id"] = admin.id
        session["username"] = admin.username
        session["full_name"] = admin.full_name
        session["role"] = admin.role
        # None = unrestricted (admin/superadmin); a list = teacher's class IDs.
        session["accessible_class_ids"] = self.auth_service.get_accessible_class_ids(admin)
        return True, "Login successful."

    def login_for_api(self, identifier: str, password: str):
        """
        Attempt a JWT-based login (used by the REST API).

        Returns:
            (token | None, error_message | None)
        """
        admin, error = self.auth_service.authenticate(identifier, password)
        if error:
            return None, error
        return self.auth_service.issue_jwt(admin), None

    def logout(self) -> None:
        """Clear the current session."""
        session.clear()

    def change_password(self, current_password: str, new_password: str, confirm_password: str) -> tuple[bool, str]:
        """
        Change the currently logged-in admin's password.

        Returns:
            (success, message)
        """
        from models import Admin

        if new_password != confirm_password:
            return False, "New password and confirmation do not match."

        admin_id = session.get("admin_id")
        admin = Admin.query.get(admin_id) if admin_id else None
        if admin is None:
            return False, "Session expired. Please log in again."

        error = self.auth_service.change_password(admin, current_password, new_password)
        if error:
            return False, error
        return True, "Password changed successfully."

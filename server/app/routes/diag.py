"""Temporary diagnostic blueprint for verifying the role decorators.

Mounted at ``/api/v1/_diag`` by the application factory. Each route is a
trivial ``200 ok`` body that is gated by exactly one of the role
decorators, so the human running the Part 8 verification can confirm:

* hitting ``/_diag/teacher-only`` with a teacher token returns 200,
* hitting it with a student token returns 403,
* hitting it with no token returns 401,
* and the symmetric set holds for ``/_diag/student-only``.

TODO(part_12_remove_diag_routes): remove this file together with the
blueprint registration in ``app/__init__.py`` once Part 12 of the build
plan retires the diagnostic endpoints. Search for the same TODO marker
in the factory to make sure both ends are removed in lockstep.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..utils.auth_decorators import (
    current_user,
    student_required,
    teacher_required,
)


diag_bp = Blueprint("diag", __name__)


@diag_bp.get("/teacher-only")
@teacher_required
def teacher_only():
    """Confirm the caller's JWT carries ``role == 'teacher'``."""
    user = current_user()
    return (
        jsonify(
            {
                "ok": True,
                "role": user.role,
                "user_id": user.id,
            }
        ),
        200,
    )


@diag_bp.get("/student-only")
@student_required
def student_only():
    """Confirm the caller's JWT carries ``role == 'student'``."""
    user = current_user()
    return (
        jsonify(
            {
                "ok": True,
                "role": user.role,
                "user_id": user.id,
            }
        ),
        200,
    )


__all__ = ["diag_bp"]

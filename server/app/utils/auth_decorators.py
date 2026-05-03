"""Authorisation decorators and the ``current_user`` lookup helper.

Each decorator wraps a Flask view, requires a valid JWT (delegated to
``flask_jwt_extended.jwt_required``), reads the ``role`` claim that the
auth subsystem injects via the additional-claims callback, and rejects
mismatches with ``403 forbidden`` using the standard error envelope from
``docs/API.md`` §1.5.

``current_user`` loads the User row identified by the JWT subject claim
and aborts with ``401 unauthorized`` if it has been deleted (or the
identity claim is malformed). Routes that need the authenticated user
should call this helper instead of re-implementing the lookup.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import abort
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User
from ..models.enums import USER_ROLE_STUDENT, USER_ROLE_TEACHER
from .responses import make_error_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _abort_unauthorized(message: str = "Authentication is required.") -> None:
    """Abort the request with the standard ``401 unauthorized`` envelope."""
    abort(make_error_response("unauthorized", message, 401))


def _abort_forbidden(message: str) -> None:
    """Abort the request with the standard ``403 forbidden`` envelope."""
    abort(make_error_response("forbidden", message, 403))


def current_user() -> User:
    """Return the SQLAlchemy ``User`` row identified by the current JWT.

    Must be called inside a request that has already passed
    ``jwt_required`` (otherwise ``get_jwt_identity`` raises). Aborts with
    ``401 unauthorized`` when the identity claim is missing, malformed,
    or refers to a row that no longer exists — that combination is the
    only safe way to react to a token whose subject has been deleted.
    """
    identity = get_jwt_identity()
    if identity is None:
        _abort_unauthorized()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        _abort_unauthorized("Authentication token is malformed.")
        return  # pragma: no cover - abort raises

    user = db.session.get(User, user_id)
    if user is None:
        _abort_unauthorized("Authenticated user no longer exists.")
    return user


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------
def _require_role(required_role: str, denial_message: str) -> Callable:
    """Build a decorator that enforces ``required_role`` on the JWT claim."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") != required_role:
                _abort_forbidden(denial_message)
            return view(*args, **kwargs)

        return wrapper

    return decorator


teacher_required = _require_role(
    USER_ROLE_TEACHER,
    "Teacher role required for this endpoint.",
)
"""Reject the caller with 403 unless the JWT carries ``role == 'teacher'``."""


student_required = _require_role(
    USER_ROLE_STUDENT,
    "Student role required for this endpoint.",
)
"""Reject the caller with 403 unless the JWT carries ``role == 'student'``."""


__all__ = ["current_user", "student_required", "teacher_required"]

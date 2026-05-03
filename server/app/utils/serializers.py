"""Serialisers that convert ORM rows into the JSON shapes documented in
``docs/API.md``.

Only the auth-related shapes live here today; routes added in later
parts will extend this module rather than duplicating field lists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from ..models import Student, Teacher, User
from ..models.enums import USER_ROLE_STUDENT, USER_ROLE_TEACHER


def _iso(value: Optional[datetime]) -> Optional[str]:
    """Render a ``datetime`` as an ISO-8601 string with a trailing ``Z``.

    Naive datetimes (sourced from SQLite, which discards timezone info)
    are treated as UTC. Returns ``None`` unchanged for null timestamps.
    """
    if value is None:
        return None
    text = value.isoformat()
    if text.endswith("+00:00"):
        text = text[: -len("+00:00")] + "Z"
    elif "+" not in text and "Z" not in text and value.tzinfo is None:
        # Naive datetime — the schema stores everything in UTC.
        text += "Z"
    return text


def serialize_user(user: User) -> Dict[str, Any]:
    """Render a User (or its Student/Teacher subclass) as a profile dict.

    The password hash is intentionally omitted. Role-specific fields are
    merged in from the joined-table subclass so the response carries the
    full profile in a single payload (per ``docs/API.md`` §2 /auth/me).
    """
    payload: Dict[str, Any] = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "created_at": _iso(user.created_at),
        "last_login": _iso(user.last_login),
    }

    if user.role == USER_ROLE_STUDENT and isinstance(user, Student):
        payload.update(
            {
                "roll_number": user.roll_number,
                "department_id": user.department_id,
                "semester": user.semester,
                "is_eligible": user.is_eligible,
            }
        )
    elif user.role == USER_ROLE_TEACHER and isinstance(user, Teacher):
        payload.update(
            {
                "employee_code": user.employee_code,
                "designation": user.designation,
                "department_id": user.department_id,
            }
        )

    return payload


__all__ = ["serialize_user"]

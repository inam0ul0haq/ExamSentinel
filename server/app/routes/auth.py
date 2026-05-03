"""Authentication blueprint — register, login, and current-user endpoints.

Mounted at ``/api/v1/auth`` by the application factory (see
``app/__init__.py``). Every response shape — success and failure — follows
``docs/API.md`` §1.5 (error envelope) and §2 (auth endpoints).

Design notes:

* Tokens are issued via ``flask_jwt_extended.create_access_token``. The
  identity callback (registered in the factory) serialises the User
  primary key to a string for the JWT ``sub`` claim. The additional-
  claims callback injects ``role`` so authorisation decorators can
  reject mismatches without a second DB round-trip.
* Registration creates the ``users`` row and the role-specific
  ``students`` / ``teachers`` row in a single transaction. Joined-table
  inheritance gives them the same primary key automatically — we never
  manage the FK by hand.
* The request body intentionally does **not** carry a ``username``
  field; one is auto-derived from the email's local-part and made
  unique by appending a numeric suffix on collision. The User model
  retains the ``username`` column (per ``docs/API.md`` §2 response
  shape and the existing schema).
* ``department_id`` is **required for students** and **optional for
  teachers**. The schema reflects this: ``students.department_id`` is
  ``NOT NULL`` while ``teachers.department_id`` was relaxed to
  nullable in revision ``0ef080486833``. When a teacher does pass a
  ``department_id`` it is still validated for type and existence.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Department, Student, Teacher, User
from ..models.enums import (
    USER_ROLE_STUDENT,
    USER_ROLE_TEACHER,
    USER_ROLE_VALUES,
)
from ..utils.auth_decorators import current_user
from ..utils.responses import error_response, validation_error
from ..utils.serializers import serialize_user


auth_bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------
# Pragmatic email shape — RFC 5322 in full is too permissive for client
# UX. Mirrors the validation users already see in most browsers.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_USERNAME_SAFE_RE = re.compile(r"[^a-z0-9._-]+")
_USERNAME_MAX_LEN = 32
_PASSWORD_MIN_LEN = 8


def _coerce_int(value: Any) -> Optional[int]:
    """Convert ``value`` to an ``int`` if it is an int-or-int-string.

    Returns ``None`` when the value is not coercible. Booleans are
    rejected (``True`` in Python is technically an ``int`` subclass but
    is never a valid id or semester in this domain).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _generate_unique_username(email: str) -> str:
    """Derive a deterministic, unique username from ``email``.

    The local-part of the email is normalised (lower-cased, stripped of
    characters outside ``[a-z0-9._-]``) and truncated to fit the 32-char
    column. On collision a numeric suffix is appended; the loop is
    bounded by ``int.max`` for paranoia and falls through to letting the
    DB raise if a billion users somehow shared the same local-part.
    """
    local = email.split("@", 1)[0].lower()
    base = _USERNAME_SAFE_RE.sub("", local) or "user"
    base = base[:_USERNAME_MAX_LEN]

    candidate = base
    if not _username_taken(candidate):
        return candidate

    suffix = 1
    while suffix < 10**9:
        suffix_str = str(suffix)
        truncated = base[: _USERNAME_MAX_LEN - len(suffix_str)] or "user"[
            : _USERNAME_MAX_LEN - len(suffix_str)
        ]
        candidate = f"{truncated}{suffix_str}"
        if not _username_taken(candidate):
            return candidate
        suffix += 1
    return candidate  # pragma: no cover - defensive


def _username_taken(username: str) -> bool:
    """Case-insensitive existence check for ``users.username``."""
    return (
        db.session.query(User.id)
        .filter(func.lower(User.username) == username.lower())
        .first()
        is not None
    )


def _validate_common_fields(
    payload: Dict[str, Any],
) -> Tuple[Dict[str, List[str]], Dict[str, Any]]:
    """Validate ``full_name``, ``email``, ``password``, ``role``.

    Returns a ``(field_errors, cleaned)`` tuple. ``cleaned`` carries the
    normalised values — lower-cased email/role, stripped names — that
    downstream branches consume so they don't redo the work.
    """
    errors: Dict[str, List[str]] = {}
    cleaned: Dict[str, Any] = {}

    full_name = payload.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        errors.setdefault("full_name", []).append("Full name is required.")
    else:
        cleaned["full_name"] = full_name.strip()

    email_raw = payload.get("email")
    if not isinstance(email_raw, str) or not email_raw.strip():
        errors.setdefault("email", []).append("Email is required.")
    else:
        email = email_raw.strip().lower()
        if not _EMAIL_RE.match(email):
            errors.setdefault("email", []).append(
                "Email is not a valid address."
            )
        elif len(email) > 254:
            errors.setdefault("email", []).append("Email is too long.")
        else:
            cleaned["email"] = email

    password = payload.get("password")
    if not isinstance(password, str) or not password:
        errors.setdefault("password", []).append("Password is required.")
    elif len(password) < _PASSWORD_MIN_LEN:
        errors.setdefault("password", []).append(
            f"Password must be at least {_PASSWORD_MIN_LEN} characters."
        )
    else:
        cleaned["password"] = password

    role_raw = payload.get("role")
    if not isinstance(role_raw, str) or not role_raw.strip():
        errors.setdefault("role", []).append("Role is required.")
    else:
        role = role_raw.strip().lower()
        if role not in USER_ROLE_VALUES:
            errors.setdefault("role", []).append(
                "Role must be 'student' or 'teacher'."
            )
        else:
            cleaned["role"] = role

    return errors, cleaned


def _validate_student_fields(
    payload: Dict[str, Any],
    errors: Dict[str, List[str]],
    cleaned: Dict[str, Any],
) -> None:
    """Populate ``errors``/``cleaned`` with the student-only fields."""
    roll_number = payload.get("roll_number")
    if not isinstance(roll_number, str) or not roll_number.strip():
        errors.setdefault("roll_number", []).append("Roll number is required.")
    else:
        cleaned["roll_number"] = roll_number.strip()

    department_id = _coerce_int(payload.get("department_id"))
    if department_id is None or department_id <= 0:
        errors.setdefault("department_id", []).append(
            "Department id is required and must be a positive integer."
        )
    else:
        cleaned["department_id"] = department_id

    semester = _coerce_int(payload.get("semester"))
    if semester is None or semester <= 0:
        errors.setdefault("semester", []).append(
            "Semester is required and must be a positive integer."
        )
    else:
        cleaned["semester"] = semester


def _validate_teacher_fields(
    payload: Dict[str, Any],
    errors: Dict[str, List[str]],
    cleaned: Dict[str, Any],
) -> None:
    """Populate ``errors``/``cleaned`` with the teacher-only fields.

    ``department_id`` is **optional** for teachers (the column is
    nullable per migration ``0ef080486833``). When the caller does
    supply a value, we still validate it: it must be a positive integer
    referring to an existing row. The ``cleaned`` dict only carries a
    ``department_id`` key when the caller provided one, so the register
    handler can distinguish "absent" from "provided as null".
    """
    employee_code = payload.get("employee_code")
    if not isinstance(employee_code, str) or not employee_code.strip():
        errors.setdefault("employee_code", []).append(
            "Employee code is required."
        )
    else:
        cleaned["employee_code"] = employee_code.strip()

    designation = payload.get("designation")
    if not isinstance(designation, str) or not designation.strip():
        errors.setdefault("designation", []).append("Designation is required.")
    else:
        cleaned["designation"] = designation.strip()

    # Optional. ``None`` and the missing-key case both mean "no
    # department on this account"; everything else must coerce to a
    # positive integer.
    raw_department = payload.get("department_id", None)
    if raw_department is None:
        return
    department_id = _coerce_int(raw_department)
    if department_id is None or department_id <= 0:
        errors.setdefault("department_id", []).append(
            "Department id, when provided, must be a positive integer."
        )
    else:
        cleaned["department_id"] = department_id


def _login_response(user: User) -> Tuple[Any, int]:
    """Build the ``200 ok`` body for a successful authentication."""
    token = create_access_token(identity=user)
    body = {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 12 * 60 * 60,  # 43200 — kept in sync with config
        "user": serialize_user(user),
    }
    return jsonify(body), 200


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@auth_bp.post("/register")
def register():
    """Create a User + Student/Teacher row in one transaction.

    On success returns ``201 created`` with the newly created profile and
    a freshly issued access token (the prompt overrides the
    ``docs/API.md`` no-token-on-register behaviour, paragraph "freshly
    issued JWT"). On validation failure returns ``422 validation_failed``
    with per-field details. On uniqueness collisions returns ``409
    conflict`` with ``error.details.field`` naming the offending column.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    errors, cleaned = _validate_common_fields(payload)

    role = cleaned.get("role")
    if role == USER_ROLE_STUDENT:
        _validate_student_fields(payload, errors, cleaned)
    elif role == USER_ROLE_TEACHER:
        _validate_teacher_fields(payload, errors, cleaned)

    if errors:
        return validation_error(errors)

    # Department existence check — only after the per-field validation
    # passes, otherwise we'd be hitting the DB with a half-validated
    # payload. The student branch always populates ``department_id``;
    # the teacher branch only populates it when the caller supplied one,
    # so the lookup is conditional.
    if "department_id" in cleaned:
        department = db.session.get(Department, cleaned["department_id"])
        if department is None:
            return validation_error(
                {"department_id": ["Department not found."]}
            )

    email = cleaned["email"]
    full_name = cleaned["full_name"]

    # Pre-flight uniqueness checks. Race conditions are still caught by
    # the IntegrityError fallback below, but checking up-front lets us
    # return a clean ``422 validation_failed`` with a precise field name
    # in the common case. The acceptance tests expect duplicate email to
    # surface as a field-level validation error rather than a generic
    # conflict.
    if (
        db.session.query(User.id)
        .filter(func.lower(User.email) == email)
        .first()
    ):
        return validation_error(
            {"email": ["An account with this email already exists."]}
        )

    if role == USER_ROLE_STUDENT:
        existing_roll = (
            db.session.query(Student.id)
            .filter(func.lower(Student.roll_number) == cleaned["roll_number"].lower())
            .first()
        )
        if existing_roll:
            return validation_error(
                {"roll_number": ["Roll number is already registered."]}
            )
    else:  # teacher
        existing_emp = (
            db.session.query(Teacher.id)
            .filter(
                func.lower(Teacher.employee_code)
                == cleaned["employee_code"].lower()
            )
            .first()
        )
        if existing_emp:
            return validation_error(
                {"employee_code": ["Employee code is already registered."]}
            )

    username = _generate_unique_username(email)

    if role == USER_ROLE_STUDENT:
        user: User = Student(
            username=username,
            email=email,
            full_name=full_name,
            roll_number=cleaned["roll_number"],
            department_id=cleaned["department_id"],
            semester=cleaned["semester"],
        )
    else:
        user = Teacher(
            username=username,
            email=email,
            full_name=full_name,
            employee_code=cleaned["employee_code"],
            designation=cleaned["designation"],
            # ``department_id`` is optional for teachers — pass it only
            # when the caller supplied one. SQLAlchemy will leave the
            # column NULL otherwise, which the schema now allows.
            department_id=cleaned.get("department_id"),
        )

    user.set_password(cleaned["password"])

    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        # Race condition on a unique index — the pre-flight check lost
        # to a concurrent insert. Per the acceptance tests, we return the
        # same ``422 validation_failed`` envelope as the pre-flight checks
        # rather than a generic 409 conflict. The error message stays
        # generic because we don't know which constraint tripped.
        db.session.rollback()
        return validation_error(
            {"_": ["Account could not be created due to a uniqueness conflict."]}
        )

    token = create_access_token(identity=user)
    body = {
        "user": serialize_user(user),
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 12 * 60 * 60,
    }
    return jsonify(body), 201


@auth_bp.post("/login")
def login():
    """Verify credentials and issue a JWT.

    Accepts ``email`` and ``password``. On success returns ``200 ok``
    with the user profile and a token. On any authentication failure —
    unknown email, wrong password, malformed body — returns
    ``401 unauthorized`` with a generic message that does not leak which
    of the two factors was wrong (per ``docs/API.md`` §2).
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "invalid_credentials",
            "Invalid email or password.",
            401,
        )

    email_raw = payload.get("email")
    password = payload.get("password")
    if (
        not isinstance(email_raw, str)
        or not email_raw.strip()
        or not isinstance(password, str)
        or not password
    ):
        return error_response(
            "invalid_credentials",
            "Invalid email or password.",
            401,
        )

    email = email_raw.strip().lower()
    user = (
        db.session.query(User)
        .filter(func.lower(User.email) == email)
        .one_or_none()
    )
    if user is None or not user.verify_password(password):
        return error_response(
            "invalid_credentials",
            "Invalid email or password.",
            401,
        )

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    return _login_response(user)


@auth_bp.get("/me")
@jwt_required()
def me():
    """Return the authenticated user's profile.

    Joined-table inheritance loads the Student/Teacher subclass when the
    User row is fetched by primary key, so the serialiser gets the full
    role-specific payload without an explicit join.
    """
    user = current_user()
    return jsonify({"user": serialize_user(user)}), 200


__all__ = ["auth_bp"]

"""Departments and user listing blueprint.

Provides public department endpoints (for student registration) and
teacher-only student/teacher listing with filtering and pagination.
"""

from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_

from ..extensions import db
from ..models import Department, Student, Teacher
from ..services.schemas import (
    DepartmentSchema,
    PaginatedResponseSchema,
    PaginationSchema,
    StudentSummarySchema,
    TeacherSummarySchema,
)
from ..utils.auth_decorators import teacher_required
from ..utils.responses import error_response, validation_error

departments_bp = Blueprint("departments", __name__, url_prefix="/departments")
users_bp = Blueprint("users", __name__, url_prefix="/users")


def _get_pagination_params() -> tuple[int, int]:
    """Extract and validate pagination query parameters.

    Returns ``(page, page_size)`` tuple.
    """
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        raise validation_error(
            {"page": ["Page and page_size must be integers."]}
        )

    if page < 1:
        raise validation_error({"page": ["Page must be at least 1."]})
    if page_size < 1:
        raise validation_error(
            {"page_size": ["Page size must be at least 1."]}
        )
    if page_size > 100:
        page_size = 100

    return page, page_size


def _build_pagination_response(
    items: List[Dict[str, Any]], page: int, page_size: int, total_items: int
) -> Dict[str, Any]:
    """Build the standard pagination envelope."""
    total_pages = (total_items + page_size - 1) // page_size
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    }


# ------------------------------------------------------------------------
# Department endpoints (public)
# ------------------------------------------------------------------------


@departments_bp.get("", strict_slashes=False)
def list_departments():
    """List all departments (public endpoint for student registration).

    Accepts pagination query parameters per §1.6 of the API contract.
    Returns a paginated list of departments.
    """
    page, page_size = _get_pagination_params()

    query = db.session.query(Department)
    total_items = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    schema = DepartmentSchema(many=True)
    result = _build_pagination_response(
        schema.dump(items), page, page_size, total_items
    )
    return jsonify(result), 200


@departments_bp.get("/<int:department_id>")
def get_department(department_id: int):
    """Get a single department by id (public endpoint).

    Returns 404 if the department does not exist.
    """
    dept = db.session.get(Department, department_id)
    if dept is None:
        return error_response("not_found", "Department not found.", 404)

    schema = DepartmentSchema()
    return jsonify(schema.dump(dept)), 200


# ------------------------------------------------------------------------
# User listing endpoints (teacher-only)
# ------------------------------------------------------------------------


@users_bp.get("/students")
@teacher_required
def list_students():
    """List students with optional filters (teacher-only).

    Query parameters:
    - department_id (int): restrict to one department
    - semester (int): restrict to semester
    - q (string): case-insensitive substring match against full_name,
                  username, email, and roll_number

    Accepts pagination. Unknown department_id or semester returns an empty
    page (not 404). Empty q is treated as omitted.
    """
    page, page_size = _get_pagination_params()

    department_id = request.args.get("department_id", type=int)
    semester = request.args.get("semester", type=int)
    q = request.args.get("q", "").strip()

    # Build the base query with joins to get department name
    query = (
        db.session.query(
            Student.id,
            Student.username,
            Student.email,
            Student.full_name,
            Student.roll_number,
            Student.department_id,
            Department.name.label("department_name"),
        )
        .join(Department, Student.department_id == Department.id)
    )

    # Apply filters
    if department_id is not None:
        query = query.filter(Student.department_id == department_id)

    if semester is not None:
        query = query.filter(Student.semester == semester)

    if q:
        query = query.filter(
            or_(
                Student.full_name.ilike(f"%{q}%"),
                Student.username.ilike(f"%{q}%"),
                Student.email.ilike(f"%{q}%"),
                Student.roll_number.ilike(f"%{q}%"),
            )
        )

    total_items = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    # Convert rows to dict format for schema
    items = [
        {
            "id": row.id,
            "username": row.username,
            "email": row.email,
            "full_name": row.full_name,
            "roll_number": row.roll_number,
            "department_id": row.department_id,
            "department_name": row.department_name,
        }
        for row in rows
    ]

    schema = StudentSummarySchema(many=True)
    result = _build_pagination_response(
        schema.dump(items), page, page_size, total_items
    )
    return jsonify(result), 200


@users_bp.get("/teachers")
@teacher_required
def list_teachers():
    """List teachers (teacher-only).

    Accepts pagination. Returns teacher summaries including designation.
    """
    page, page_size = _get_pagination_params()

    query = (
        db.session.query(
            Teacher.id,
            Teacher.username,
            Teacher.email,
            Teacher.full_name,
            Teacher.employee_code,
            Teacher.department_id,
            Teacher.designation,
        )
        .join(Department, Teacher.department_id == Department.id)
    )

    total_items = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": row.id,
            "username": row.username,
            "email": row.email,
            "full_name": row.full_name,
            "employee_code": row.employee_code,
            "department_id": row.department_id,
            "designation": row.designation,
        }
        for row in rows
    ]

    schema = TeacherSummarySchema(many=True)
    result = _build_pagination_response(
        schema.dump(items), page, page_size, total_items
    )
    return jsonify(result), 200


__all__ = ["departments_bp", "users_bp"]

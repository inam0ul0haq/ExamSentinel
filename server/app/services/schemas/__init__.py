"""Marshmallow schemas for API serialization.

All schemas are kept in this module for discoverability. Each schema
is responsible for serializing ORM rows into the JSON shapes documented
in ``docs/API.md``.
"""

from __future__ import annotations

from marshmallow import Schema, fields, validate, validates_schema, ValidationError
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from sqlalchemy import func

from ...extensions import db
from ...models import Course, Department, Enrollment, Student, Teacher, Exam


class PaginationSchema(Schema):
    """Standard pagination envelope per §1.6 of the API contract."""

    page = fields.Integer(required=True)
    page_size = fields.Integer(required=True)
    total_items = fields.Integer(required=True)
    total_pages = fields.Integer(required=True)


class PaginatedResponseSchema(Schema):
    """Paginated list response envelope."""

    items = fields.List(fields.Dict(), required=True)
    pagination = fields.Nested(PaginationSchema, required=True)


class DepartmentSchema(SQLAlchemyAutoSchema):
    """Department summary for list and detail endpoints."""

    class Meta:
        model = Department
        fields = ["id", "name", "code", "created_at"]
        # Don't auto-serialize datetime, we'll handle it in routes
        include_relationships = False


class StudentSummarySchema(Schema):
    """Student summary for /users/students list endpoint."""

    id = fields.Integer(required=True)
    username = fields.String(required=True)
    email = fields.String(required=True)
    full_name = fields.String(required=True)
    roll_number = fields.String(required=True)
    department_id = fields.Integer(required=True)
    department_name = fields.String(required=True)


class TeacherSummarySchema(Schema):
    """Teacher summary for /users/teachers list endpoint."""

    id = fields.Integer(required=True)
    username = fields.String(required=True)
    email = fields.String(required=True)
    full_name = fields.String(required=True)
    employee_code = fields.String(required=True)
    department_id = fields.Integer(required=True)
    designation = fields.String(required=True)


class CourseSummarySchema(Schema):
    """Course summary for list-my-courses endpoint."""

    id = fields.Integer(required=True)
    code = fields.String(required=True)
    title = fields.String(required=True)
    description = fields.String(required=True, allow_none=True)
    teacher_id = fields.Integer(required=True)
    teacher_name = fields.String(required=True)
    exam_count = fields.Integer(required=True)
    # Role-specific fields
    enrollment_count = fields.Integer(required=True, allow_none=True)
    active_exam_count = fields.Integer(required=True, allow_none=True)


class CourseDetailSchema(Schema):
    """Full course detail for GET /courses/{id} endpoint."""

    id = fields.Integer(required=True)
    code = fields.String(required=True)
    title = fields.String(required=True)
    description = fields.String(required=True, allow_none=True)
    teacher_id = fields.Integer(required=True)
    teacher_name = fields.String(required=True)
    created_at = fields.DateTime(required=True)
    exam_count = fields.Integer(required=True)
    # Teacher-only field: enrolled students
    enrolled_students = fields.List(
        fields.Dict(), required=True, allow_none=True
    )


class EnrollmentSchema(Schema):
    """Enrollment detail for create and list endpoints."""

    id = fields.Integer(required=True)
    course_id = fields.Integer(required=True)
    student_id = fields.Integer(required=True)
    student_full_name = fields.String(required=True)
    student_email = fields.String(required=True)
    student_roll_number = fields.String(required=True)
    enrolled_at = fields.DateTime(required=True)
    status = fields.String(required=True)


class ExamBriefSchema(Schema):
    """Brief exam summary for course detail."""

    id = fields.Integer(required=True)
    title = fields.String(required=True)
    is_active = fields.Boolean(required=True)


__all__ = [
    "PaginationSchema",
    "PaginatedResponseSchema",
    "DepartmentSchema",
    "StudentSummarySchema",
    "TeacherSummarySchema",
    "CourseSummarySchema",
    "CourseDetailSchema",
    "EnrollmentSchema",
    "ExamBriefSchema",
]

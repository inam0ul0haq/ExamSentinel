"""Courses and enrollments blueprint.

Provides course CRUD operations (teacher-owned only) and enrollment
management. Students can only view courses they're enrolled in.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Course, Enrollment, Exam, Student, Teacher, User
from ..models.enums import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_DROPPED,
    EnrollmentStatusEnum,
)
from ..services.schemas import (
    CourseDetailSchema,
    CourseSummarySchema,
    EnrollmentSchema,
    ExamBriefSchema,
)
from ..utils.auth_decorators import current_user, teacher_required, jwt_required
from ..utils.responses import error_response, validation_error

courses_bp = Blueprint("courses", __name__, url_prefix="/courses")


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


def _validate_course_code(code: str, exclude_id: Optional[int] = None):
    """Validate course code uniqueness.

    Returns validation_error response if the code already exists
    (excluding the course with id=exclude_id if provided).
    """
    query = db.session.query(Course.id).filter(
        func.lower(Course.code) == code.lower()
    )
    if exclude_id is not None:
        query = query.filter(Course.id != exclude_id)

    if query.first():
        return validation_error(
            {"code": ["Course code already exists."]}
        )


# ------------------------------------------------------------------------
# Course CRUD (teacher-owned only)
# ------------------------------------------------------------------------


@courses_bp.post("")
@teacher_required
def create_course():
    """Create a new course (teacher-only).

    The owning teacher is implicit from the JWT; the body cannot
    override teacher_id. Course code must be unique.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    errors: Dict[str, List[str]] = {}
    cleaned: Dict[str, Any] = {}

    # Validate title
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.setdefault("title", []).append("Title is required.")
    elif len(title) > 120:
        errors.setdefault("title", []).append(
            "Title must be at most 120 characters."
        )
    else:
        cleaned["title"] = title.strip()

    # Validate code
    code = payload.get("code")
    if not isinstance(code, str) or not code.strip():
        errors.setdefault("code", []).append("Course code is required.")
    elif len(code) < 2 or len(code) > 20:
        errors.setdefault("code", []).append(
            "Course code must be between 2 and 20 characters."
        )
    elif not code.replace("-", "").replace("_", "").isalnum():
        errors.setdefault("code", []).append(
            "Course code must be alphanumeric (hyphens and underscores allowed)."
        )
    else:
        cleaned["code"] = code.strip()
        validation_result = _validate_course_code(cleaned["code"])
        if validation_result:
            return validation_result

    # Validate description (optional)
    description = payload.get("description")
    if description is not None:
        if not isinstance(description, str):
            errors.setdefault("description", []).append(
                "Description must be a string if provided."
            )
        elif len(description) > 2000:
            errors.setdefault("description", []).append(
                "Description must be at most 2000 characters."
            )
        else:
            cleaned["description"] = description.strip()

    if errors:
        return validation_error(errors)

    # Create the course with the current teacher as owner
    teacher = current_user()
    course = Course(
        title=cleaned["title"],
        code=cleaned["code"],
        description=cleaned.get("description"),
        teacher_id=teacher.id,
    )

    try:
        db.session.add(course)
        db.session.commit()
    except IntegrityError:
        # Race condition on code uniqueness
        db.session.rollback()
        return validation_error(
            {"code": ["Course code already exists."]}
        )

    # Build response
    body = {
        "id": course.id,
        "title": course.title,
        "code": course.code,
        "description": course.description,
        "teacher_id": course.teacher_id,
        "teacher_name": teacher.full_name,
        "created_at": course.created_at,
        "enrollment_count": 0,
    }
    return jsonify(body), 201


@courses_bp.get("/<int:course_id>")
@jwt_required()
def get_course(course_id: int):
    """Get course detail (student or teacher).

    Teacher must own the course, or student must be enrolled in it.
    Returns course fields plus exam_count and (for teachers only)
    enrolled students list.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()

    # Authorization: teacher must own, student must be enrolled
    if user.role == "teacher":
        if course.teacher_id != user.id:
            return error_response(
                "forbidden",
                "You do not own this course.",
                403,
            )
    else:  # student
        enrollment = (
            db.session.query(Enrollment.id)
            .filter(
                Enrollment.student_id == user.id,
                Enrollment.course_id == course_id,
                Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
            )
            .first()
        )
        if not enrollment:
            return error_response(
                "forbidden",
                "You are not enrolled in this course.",
                403,
            )

    # Count exams
    exam_count = db.session.query(func.count(Exam.id)).filter(
        Exam.course_id == course_id
    ).scalar()

    # Build response
    body = {
        "id": course.id,
        "code": course.code,
        "title": course.title,
        "description": course.description,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.full_name,
        "created_at": course.created_at,
        "exam_count": exam_count,
    }

    # Teacher-only: enrolled students
    if user.role == "teacher":
        enrolled = (
            db.session.query(
                Student.id,
                Student.username,
                Student.email,
                Student.full_name,
                Student.roll_number,
            )
            .join(Enrollment, Enrollment.student_id == Student.id)
            .filter(
                Enrollment.course_id == course_id,
                Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
            )
            .all()
        )
        body["enrolled_students"] = [
            {
                "id": s.id,
                "username": s.username,
                "email": s.email,
                "full_name": s.full_name,
                "roll_number": s.roll_number,
            }
            for s in enrolled
        ]
    else:
        body["enrolled_students"] = None

    return jsonify(body), 200


@courses_bp.patch("/<int:course_id>")
@teacher_required
def update_course(course_id: int):
    """Update a course (teacher-only, must own).

    Accepts any subset of title, code, description. Code uniqueness
    is re-checked on change.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()
    if course.teacher_id != user.id:
        return error_response(
            "forbidden",
            "You do not own this course.",
            403,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    if not payload:
        return validation_error(
            {"_": ["At least one field must be provided for update."]}
        )

    errors: Dict[str, List[str]] = {}
    updated = False

    # Update title if provided
    if "title" in payload:
        title = payload["title"]
        if not isinstance(title, str) or not title.strip():
            errors.setdefault("title", []).append("Title is required.")
        elif len(title) > 120:
            errors.setdefault("title", []).append(
                "Title must be at most 120 characters."
            )
        else:
            course.title = title.strip()
            updated = True

    # Update code if provided
    if "code" in payload:
        code = payload["code"]
        if not isinstance(code, str) or not code.strip():
            errors.setdefault("code", []).append("Course code is required.")
        elif len(code) < 2 or len(code) > 20:
            errors.setdefault("code", []).append(
                "Course code must be between 2 and 20 characters."
            )
        elif not code.replace("-", "").replace("_", "").isalnum():
            errors.setdefault("code", []).append(
                "Course code must be alphanumeric."
            )
        else:
            validation_result = _validate_course_code(code.strip(), exclude_id=course_id)
            if validation_result:
                return validation_result
            course.code = code.strip()
            updated = True

    # Update description if provided
    if "description" in payload:
        description = payload["description"]
        if description is not None:
            if not isinstance(description, str):
                errors.setdefault("description", []).append(
                    "Description must be a string if provided."
                )
            elif len(description) > 2000:
                errors.setdefault("description", []).append(
                    "Description must be at most 2000 characters."
                )
            else:
                course.description = description.strip()
                updated = True
        else:
            course.description = None
            updated = True

    if errors:
        return validation_error(errors)

    if not updated:
        return validation_error(
            {"_": ["At least one field must be provided for update."]}
        )

    db.session.commit()

    # Build response
    body = {
        "id": course.id,
        "title": course.title,
        "code": course.code,
        "description": course.description,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.full_name,
        "created_at": course.created_at.isoformat(),
        "enrollment_count": len(
            [e for e in course.enrollments if e.status == ENROLLMENT_STATUS_ACTIVE]
        ),
    }
    return jsonify(body), 200


@courses_bp.delete("/<int:course_id>")
@teacher_required
def delete_course(course_id: int):
    """Delete a course (teacher-only, must own).

    TODO: Rejected with 409 if any exam in the course has at least one
    submitted or reviewed session (data integrity). This check requires
    the Session model which is implemented in Part 9 (Sessions and Answers).
    For now, deletion is always allowed since no exams/sessions exist yet.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()
    if course.teacher_id != user.id:
        return error_response(
            "forbidden",
            "You do not own this course.",
            403,
        )

    # TODO: Add session check once Session model exists (Part 9)
    # from ..models import Session as ExamSession
    # from ..models.enums import SessionStatusEnum

    db.session.delete(course)
    db.session.commit()

    return "", 204


# ------------------------------------------------------------------------
# List my courses (student or teacher)
# ------------------------------------------------------------------------


@courses_bp.get("/me")
@jwt_required()
def list_my_courses():
    """List courses visible to the caller (student or teacher).

    For teachers: courses they own.
    For students: courses where active enrollment exists.
    Accepts pagination.
    """
    page, page_size = _get_pagination_params()
    user = current_user()

    if user.role == "teacher":
        # List courses owned by this teacher
        query = db.session.query(Course).filter(Course.teacher_id == user.id)
        total_items = query.count()
        courses = query.offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for c in courses:
            enrollment_count = len(
                [e for e in c.enrollments if e.status == ENROLLMENT_STATUS_ACTIVE]
            )
            exam_count = len(c.exams)
            items.append({
                "id": c.id,
                "code": c.code,
                "title": c.title,
                "description": c.description,
                "teacher_id": c.teacher_id,
                "teacher_name": c.teacher.full_name,
                "exam_count": exam_count,
                "enrollment_count": enrollment_count,
                "active_exam_count": None,
            })

    else:  # student
        # List courses where student has active enrollment
        query = (
            db.session.query(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .filter(
                Enrollment.student_id == user.id,
                Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
            )
        )
        total_items = query.count()
        courses = query.offset((page - 1) * page_size).limit(page_size).all()

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        items = []
        for c in courses:
            exam_count = len(c.exams)
            # Count active exams (within window and is_active=true)
            active_exam_count = sum(
                1
                for e in c.exams
                if e.is_active
                and e.start_window <= now
                and e.end_window >= now
            )
            items.append({
                "id": c.id,
                "code": c.code,
                "title": c.title,
                "description": c.description,
                "teacher_id": c.teacher_id,
                "teacher_name": c.teacher.full_name,
                "exam_count": exam_count,
                "enrollment_count": None,
                "active_exam_count": active_exam_count,
            })

    schema = CourseSummarySchema(many=True)
    result = _build_pagination_response(
        schema.dump(items), page, page_size, total_items
    )
    return jsonify(result), 200


# ------------------------------------------------------------------------
# Enrollment management (teacher-only, must own course)
# ------------------------------------------------------------------------


@courses_bp.post("/<int:course_id>/enrollments")
@teacher_required
def enroll_student(course_id: int):
    """Enroll a student by email (teacher-only, must own course).

    Body: { "student_email": "..." }
    Returns 404 if email not found, 422 if email resolves to a teacher,
    409 if already enrolled. Re-activates previously dropped enrollments.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()
    if course.teacher_id != user.id:
        return error_response(
            "forbidden",
            "You do not own this course.",
            403,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    student_email = payload.get("student_email")
    if not isinstance(student_email, str) or not student_email.strip():
        return validation_error(
            {"student_email": ["Student email is required."]}
        )

    # Look up student by email
    student = (
        db.session.query(Student)
        .filter(func.lower(Student.email) == student_email.strip().lower())
        .first()
    )
    if not student:
        return error_response(
            "not_found",
            "Student not found.",
            404,
            details={"field": "student_email"},
        )

    # Check if already enrolled (active or dropped)
    existing = (
        db.session.query(Enrollment)
        .filter(
            Enrollment.student_id == student.id,
            Enrollment.course_id == course_id,
        )
        .first()
    )

    if existing:
        if existing.status == ENROLLMENT_STATUS_ACTIVE:
            return error_response(
                "conflict",
                "Student is already enrolled in this course.",
                409,
            )
        # Re-activate dropped enrollment
        existing.status = ENROLLMENT_STATUS_ACTIVE
        db.session.commit()

        body = {
            "id": existing.id,
            "course_id": existing.course_id,
            "student_id": existing.student_id,
            "student_full_name": student.full_name,
            "student_email": student.email,
            "student_roll_number": student.roll_number,
            "enrolled_at": existing.enrolled_at.isoformat(),
            "status": str(existing.status),
        }
        return jsonify(body), 201

    # Create new enrollment
    enrollment = Enrollment(
        student_id=student.id,
        course_id=course_id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db.session.add(enrollment)
    db.session.commit()

    body = {
        "id": enrollment.id,
        "course_id": enrollment.course_id,
        "student_id": enrollment.student_id,
        "student_full_name": student.full_name,
        "student_email": student.email,
        "student_roll_number": student.roll_number,
        "enrolled_at": enrollment.enrolled_at.isoformat(),
        "status": str(enrollment.status),
    }
    return jsonify(body), 201


@courses_bp.delete("/<int:course_id>/enrollments/<int:enrollment_id>")
@teacher_required
def drop_enrollment(course_id: int, enrollment_id: int):
    """Drop an enrollment (teacher-only, must own course).

    Sets status to 'dropped' (preserves audit trail). Returns 404 if
    enrollment not found.

    TODO: Rejected with 409 if student has any in_progress session in the
    course. This check requires the Session model (Part 9).
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()
    if course.teacher_id != user.id:
        return error_response(
            "forbidden",
            "You do not own this course.",
            403,
        )

    enrollment = db.session.get(Enrollment, enrollment_id)
    if enrollment is None:
        return error_response("not_found", "Enrollment not found.", 404)

    if enrollment.course_id != course_id:
        return error_response("not_found", "Enrollment not found.", 404)

    # TODO: Add in_progress session check once Session model exists (Part 9)
    # from ..models import Session as ExamSession
    # from ..models.enums import SessionStatusEnum

    enrollment.status = ENROLLMENT_STATUS_DROPPED
    db.session.commit()

    return "", 204


@courses_bp.get("/<int:course_id>/enrollments")
@teacher_required
def list_enrollments(course_id: int):
    """List enrollments for a course (teacher-only, must own).

    Accepts pagination and optional status filter (active or dropped).
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()
    if course.teacher_id != user.id:
        return error_response(
            "forbidden",
            "You do not own this course.",
            403,
        )

    page, page_size = _get_pagination_params()
    status_filter = request.args.get("status", "active").strip().lower()

    if status_filter not in {"active", "dropped"}:
        return validation_error(
            {"status": ["Status must be 'active' or 'dropped'."]}
        )

    status_enum = (
        ENROLLMENT_STATUS_ACTIVE
        if status_filter == "active"
        else EnrollmentStatusEnum.DROPPED
    )

    query = (
        db.session.query(Enrollment)
        .filter(
            Enrollment.course_id == course_id,
            Enrollment.status == status_enum,
        )
        .join(Student, Enrollment.student_id == Student.id)
    )
    total_items = query.count()
    enrollments = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for e in enrollments:
        dept = e.student.department
        items.append({
            "id": e.id,
            "course_id": e.course_id,
            "student_id": e.student_id,
            "student_full_name": e.student.full_name,
            "student_email": e.student.email,
            "student_roll_number": e.student.roll_number,
            "student_semester": e.student.semester,
            "student_department_name": dept.name if dept else None,
            "enrolled_at": e.enrolled_at,
            "status": str(e.status),
        })

    schema = EnrollmentSchema(many=True)
    result = _build_pagination_response(
        schema.dump(items), page, page_size, total_items
    )
    return jsonify(result), 200


@courses_bp.get("/<int:course_id>/students")
@teacher_required
def list_course_students(course_id: int):
    """List enrolled students for a course (teacher-only, must own).

    Returns a list of student summaries for all active enrollments.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()
    if course.teacher_id != user.id:
        return error_response(
            "forbidden",
            "You do not own this course.",
            403,
        )

    students = (
        db.session.query(
            Student.id,
            Student.username,
            Student.email,
            Student.full_name,
            Student.roll_number,
            Student.department_id,
        )
        .join(Enrollment, Enrollment.student_id == Student.id)
        .filter(
            Enrollment.course_id == course_id,
            Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
        )
        .all()
    )

    items = [
        {
            "id": s.id,
            "username": s.username,
            "email": s.email,
            "full_name": s.full_name,
            "roll_number": s.roll_number,
            "department_id": s.department_id,
        }
        for s in students
    ]

    return jsonify(items), 200


__all__ = ["courses_bp"]

"""Exams blueprint.

Provides exam CRUD operations, question management, and activation
for teachers, plus active exam listing for students.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Course, Exam, Question
from ..models.enums import QUESTION_TYPE_MCQ
from ..services.exam_service import (
    activate_exam,
    can_delete_exam,
    can_edit_exam,
    create_exam,
    deactivate_exam,
    get_student_active_exams,
    replace_questions,
    validate_exam_ownership,
)
from ..utils.auth_decorators import current_user, jwt_required, student_required, teacher_required
from ..utils.responses import error_response, validation_error

exams_bp = Blueprint("exams", __name__)


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


def _serialize_question(question: Question, include_correct: bool = False) -> Dict[str, Any]:
    """Serialize a question for API response.

    Strips correct_answer unless include_correct is True.
    """
    data = {
        "id": question.id,
        "question_text": question.prompt,
        "question_type": question.question_type,
        "marks": question.marks,
        "order_index": question.order_index,
    }

    if question.question_type == QUESTION_TYPE_MCQ:
        options = [
            q for q in [question.option_a, question.option_b, question.option_c, question.option_d] if q
        ]
        data["options"] = options
        if include_correct:
            option_map = {
                "A": question.option_a,
                "B": question.option_b,
                "C": question.option_c,
                "D": question.option_d,
            }
            data["correct_answer"] = option_map.get(question.correct_option)

    return data


# ------------------------------------------------------------------------
# Course-scoped exam endpoints (teacher-only)
# ------------------------------------------------------------------------


@exams_bp.post("/courses/<int:course_id>/exams")
@teacher_required
def create_exam_endpoint(course_id: int):
    """Create a new exam with questions (teacher-only, must own course)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    errors: Dict[str, List[str]] = {}

    # Validate title
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.setdefault("title", []).append("Title is required.")
    elif len(title) > 200:
        errors.setdefault("title", []).append("Title must be at most 200 characters.")

    # Validate description (optional)
    description = payload.get("description")
    if description is not None:
        if not isinstance(description, str):
            errors.setdefault("description", []).append("Description must be a string if provided.")
        elif len(description) > 4000:
            errors.setdefault("description", []).append("Description must be at most 4000 characters.")

    # Validate duration_minutes
    duration_minutes = payload.get("duration_minutes")
    if not isinstance(duration_minutes, int) or duration_minutes <= 0 or duration_minutes > 600:
        errors.setdefault("duration_minutes", []).append("Duration must be between 1 and 600 minutes.")

    # Validate start_window and end_window (optional)
    start_window = None
    end_window = None

    start_window_str = payload.get("start_window")
    if start_window_str:
        try:
            start_window = datetime.fromisoformat(start_window_str)
        except (ValueError, TypeError):
            errors.setdefault("start_window", []).append("Invalid ISO-8601 timestamp.")

    end_window_str = payload.get("end_window")
    if end_window_str:
        try:
            end_window = datetime.fromisoformat(end_window_str)
        except (ValueError, TypeError):
            errors.setdefault("end_window", []).append("Invalid ISO-8601 timestamp.")

    # Validate questions
    questions = payload.get("questions")
    if not isinstance(questions, list):
        errors.setdefault("questions", []).append("Questions must be an array.")

    if errors:
        return validation_error(errors)

    user = current_user()

    try:
        exam = create_exam(
            course_id=course_id,
            title=title.strip(),
            description=description.strip() if description else None,
            duration_minutes=duration_minutes,
            start_window=start_window,
            end_window=end_window,
            questions=questions,
            teacher_id=user.id,
        )
    except Exception as e:
        if isinstance(e, tuple):
            return e  # error_response tuple
        raise

    # Build response with questions
    body = {
        "id": exam.id,
        "course_id": exam.course_id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "start_window": exam.start_window.isoformat() if exam.start_window else None,
        "end_window": exam.end_window.isoformat() if exam.end_window else None,
        "is_active": exam.is_active,
        "created_at": exam.created_at.isoformat(),
        "questions": [_serialize_question(q, include_correct=True) for q in exam.questions],
    }
    return jsonify(body), 201


# ------------------------------------------------------------------------
# Exam CRUD endpoints
# ------------------------------------------------------------------------


@exams_bp.get("/exams/<int:exam_id>")
@jwt_required()
def get_exam(exam_id: int):
    """Get exam by id (teacher or student).

    Teacher who owns the course gets full exam with correct answers.
    Student enrolled in course gets summary only if exam is active.
    """
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    user = current_user()

    # Teacher view
    if user.role == "teacher":
        course = db.session.get(Course, exam.course_id)
        if course.teacher_id != user.id:
            return error_response("forbidden", "You do not own this exam's course.", 403)

        body = {
            "id": exam.id,
            "course_id": exam.course_id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "start_window": exam.start_window.isoformat() if exam.start_window else None,
            "end_window": exam.end_window.isoformat() if exam.end_window else None,
            "is_active": exam.is_active,
            "created_at": exam.created_at.isoformat(),
            "questions": [_serialize_question(q, include_correct=True) for q in exam.questions],
        }
        return jsonify(body), 200

    # Student view
    else:
        from ..models import Enrollment
        from ..models.enums import ENROLLMENT_STATUS_ACTIVE

        enrollment = (
            db.session.query(Enrollment.id)
            .filter(
                Enrollment.student_id == user.id,
                Enrollment.course_id == exam.course_id,
                Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
            )
            .first()
        )

        if not enrollment:
            return error_response("forbidden", "You are not enrolled in this exam's course.", 403)

        # Student only gets summary (no questions) unless exam is active
        body = {
            "id": exam.id,
            "course_id": exam.course_id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "start_window": exam.start_window.isoformat() if exam.start_window else None,
            "end_window": exam.end_window.isoformat() if exam.end_window else None,
            "is_active": exam.is_active,
            "question_count": len(exam.questions),
        }
        return jsonify(body), 200


@exams_bp.patch("/exams/<int:exam_id>")
@teacher_required
def update_exam(exam_id: int):
    """Update exam metadata (teacher-only, must own course)."""
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    course = db.session.get(Course, exam.course_id)
    user = current_user()
    if course.teacher_id != user.id:
        return error_response("forbidden", "You do not own this exam's course.", 403)

    # Check if exam can be edited
    if not can_edit_exam(exam):
        return error_response(
            "conflict",
            "Cannot edit exam with active sessions.",
            409,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    if not payload:
        return validation_error({"_": ["At least one field must be provided for update."]})

    errors: Dict[str, List[str]] = {}
    updated = False

    # Update title
    if "title" in payload:
        title = payload["title"]
        if not isinstance(title, str) or not title.strip():
            errors.setdefault("title", []).append("Title is required.")
        elif len(title) > 200:
            errors.setdefault("title", []).append("Title must be at most 200 characters.")
        else:
            exam.title = title.strip()
            updated = True

    # Update description
    if "description" in payload:
        description = payload["description"]
        if description is not None:
            if not isinstance(description, str):
                errors.setdefault("description", []).append("Description must be a string if provided.")
            elif len(description) > 4000:
                errors.setdefault("description", []).append("Description must be at most 4000 characters.")
            else:
                exam.description = description.strip()
                updated = True
        else:
            exam.description = None
            updated = True

    # Update duration_minutes
    if "duration_minutes" in payload:
        duration_minutes = payload["duration_minutes"]
        if not isinstance(duration_minutes, int) or duration_minutes <= 0 or duration_minutes > 600:
            errors.setdefault("duration_minutes", []).append("Duration must be between 1 and 600 minutes.")
        else:
            exam.duration_minutes = duration_minutes
            updated = True

    # Update start_window
    if "start_window" in payload:
        start_window_str = payload["start_window"]
        if start_window_str:
            try:
                exam.start_window = datetime.fromisoformat(start_window_str)
                updated = True
            except (ValueError, TypeError):
                errors.setdefault("start_window", []).append("Invalid ISO-8601 timestamp.")
        else:
            exam.start_window = None
            updated = True

    # Update end_window
    if "end_window" in payload:
        end_window_str = payload["end_window"]
        if end_window_str:
            try:
                exam.end_window = datetime.fromisoformat(end_window_str)
                updated = True
            except (ValueError, TypeError):
                errors.setdefault("end_window", []).append("Invalid ISO-8601 timestamp.")
        else:
            exam.end_window = None
            updated = True

    if errors:
        return validation_error(errors)

    if not updated:
        return validation_error({"_": ["At least one field must be provided for update."]})

    # Validate window if both are set
    if exam.start_window and exam.end_window and exam.end_window <= exam.start_window:
        return validation_error(
            {"end_window": ["End window must be after start window."]}
        )

    db.session.commit()
    db.session.refresh(exam)

    body = {
        "id": exam.id,
        "course_id": exam.course_id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "start_window": exam.start_window.isoformat() if exam.start_window else None,
        "end_window": exam.end_window.isoformat() if exam.end_window else None,
        "is_active": exam.is_active,
        "created_at": exam.created_at.isoformat(),
        "questions": [_serialize_question(q, include_correct=True) for q in exam.questions],
    }
    return jsonify(body), 200


@exams_bp.delete("/exams/<int:exam_id>")
@teacher_required
def delete_exam(exam_id: int):
    """Delete an exam (teacher-only, must own course)."""
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    course = db.session.get(Course, exam.course_id)
    user = current_user()
    if course.teacher_id != user.id:
        return error_response("forbidden", "You do not own this exam's course.", 403)

    if not can_delete_exam(exam):
        return error_response(
            "conflict",
            "Cannot delete exam with submitted or reviewed sessions.",
            409,
        )

    db.session.delete(exam)
    db.session.commit()

    return "", 204


# ------------------------------------------------------------------------
# Question management endpoints
# ------------------------------------------------------------------------


@exams_bp.put("/exams/<int:exam_id>/questions")
@teacher_required
def replace_questions_endpoint(exam_id: int):
    """Replace the exam's question set (teacher-only, must own course)."""
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    course = db.session.get(Course, exam.course_id)
    user = current_user()
    if course.teacher_id != user.id:
        return error_response("forbidden", "You do not own this exam's course.", 403)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    questions = payload.get("questions")
    if not isinstance(questions, list):
        return validation_error({"questions": ["Questions must be an array."]})

    try:
        exam = replace_questions(exam, questions)
    except Exception as e:
        if hasattr(e, "get_response"):
            return e.get_response()
        raise

    body = {
        "id": exam.id,
        "course_id": exam.course_id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "start_window": exam.start_window.isoformat() if exam.start_window else None,
        "end_window": exam.end_window.isoformat() if exam.end_window else None,
        "is_active": exam.is_active,
        "created_at": exam.created_at.isoformat(),
        "questions": [_serialize_question(q, include_correct=True) for q in exam.questions],
    }
    return jsonify(body), 200


# ------------------------------------------------------------------------
# Activation endpoints
# ------------------------------------------------------------------------


@exams_bp.post("/exams/<int:exam_id>/activate")
@teacher_required
def activate_exam_endpoint(exam_id: int):
    """Activate an exam (teacher-only, must own course)."""
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    course = db.session.get(Course, exam.course_id)
    user = current_user()
    if course.teacher_id != user.id:
        return error_response("forbidden", "You do not own this exam's course.", 403)

    try:
        exam = activate_exam(exam)
    except Exception as e:
        if isinstance(e, tuple):
            return e  # error_response tuple
        raise

    body = {
        "id": exam.id,
        "course_id": exam.course_id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "start_window": exam.start_window.isoformat() if exam.start_window else None,
        "end_window": exam.end_window.isoformat() if exam.end_window else None,
        "is_active": exam.is_active,
        "created_at": exam.created_at.isoformat(),
    }
    return jsonify(body), 200


@exams_bp.post("/exams/<int:exam_id>/deactivate")
@teacher_required
def deactivate_exam_endpoint(exam_id: int):
    """Deactivate an exam (teacher-only, must own course)."""
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    course = db.session.get(Course, exam.course_id)
    user = current_user()
    if course.teacher_id != user.id:
        return error_response("forbidden", "You do not own this exam's course.", 403)

    exam = deactivate_exam(exam)

    body = {
        "id": exam.id,
        "course_id": exam.course_id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "start_window": exam.start_window.isoformat() if exam.start_window else None,
        "end_window": exam.end_window.isoformat() if exam.end_window else None,
        "is_active": exam.is_active,
        "created_at": exam.created_at.isoformat(),
    }
    return jsonify(body), 200


# ------------------------------------------------------------------------
# Course-scoped exam listing (teacher OR enrolled student)
# ------------------------------------------------------------------------


@exams_bp.get("/courses/<int:course_id>/exams")
@jwt_required()
def list_course_exams(course_id: int):
    """List exams for a course.

    Teachers who own the course see all exams with correct answers.
    Students enrolled in the course see exam summaries with their
    per-exam session status.
    """
    from ..models import Enrollment
    from ..models.enums import ENROLLMENT_STATUS_ACTIVE
    from ..models.exam_session import ExamSession

    course = db.session.get(Course, course_id)
    if course is None:
        return error_response("not_found", "Course not found.", 404)

    user = current_user()

    if user.role == "teacher":
        if course.teacher_id != user.id:
            return error_response("forbidden", "You do not own this course.", 403)
    else:
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
            return error_response("forbidden", "You are not enrolled in this course.", 403)

    page, page_size = _get_pagination_params()
    query = db.session.query(Exam).filter(Exam.course_id == course_id)
    total_items = query.count()
    exams = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for exam in exams:
        item = {
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "start_window": exam.start_window.isoformat() if exam.start_window else None,
            "end_window": exam.end_window.isoformat() if exam.end_window else None,
            "is_active": exam.is_active,
            "question_count": len(exam.questions),
            "total_marks": exam.total_marks,
        }
        if user.role == "teacher":
            item["questions"] = [_serialize_question(q, include_correct=True) for q in exam.questions]
        else:
            session = (
                db.session.query(ExamSession)
                .filter(
                    ExamSession.exam_id == exam.id,
                    ExamSession.student_id == user.id,
                )
                .first()
            )
            item["session_status"] = str(session.status) if session else None
            item["session_id"] = session.id if session else None
        items.append(item)

    result = _build_pagination_response(items, page, page_size, total_items)
    return jsonify(result), 200


# ------------------------------------------------------------------------
# Student active exams endpoint
# ------------------------------------------------------------------------


@exams_bp.get("/exams/active")
@student_required
def get_active_exams():
    """List active exams for the student."""
    page, page_size = _get_pagination_params()
    user = current_user()

    items, total_items = get_student_active_exams(user.id, page, page_size)

    result = _build_pagination_response(items, page, page_size, total_items)
    return jsonify(result), 200


__all__ = ["exams_bp"]

"""Teacher reporting blueprint.

All endpoints mount under ``/api/v1/teacher`` and require the
``teacher_required`` decorator. Ownership of the underlying exam / session
is checked inside each handler.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Exam
from ..models.exam_session import ExamSession
from ..services.teacher_report_service import (
    assert_teacher_owns_exam,
    assert_teacher_owns_session,
    get_exam_analytics,
    get_session_detail,
    grade_session,
    list_exam_sessions,
)
from ..utils.auth_decorators import current_user, teacher_required
from ..utils.responses import error_response, validation_error


teacher_reports_bp = Blueprint("teacher_reports", __name__)


def _get_pagination_params() -> Tuple[int, int, Any]:
    """Extract and validate ``?page`` and ``?page_size`` query params.

    Returns ``(page, page_size, error_or_None)``.
    """
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        return 0, 0, validation_error(
            {"page": ["page and page_size must be integers."]}
        )

    if page < 1:
        return 0, 0, validation_error({"page": ["page must be at least 1."]})
    if page_size < 1:
        return 0, 0, validation_error(
            {"page_size": ["page_size must be at least 1."]}
        )
    if page_size > 100:
        page_size = 100
    return page, page_size, None


def _envelope(items: List[Dict[str, Any]], page: int, page_size: int,
              total_items: int) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# GET /exams/<id>/sessions
# ---------------------------------------------------------------------------
@teacher_reports_bp.get("/exams/<int:exam_id>/sessions")
@teacher_required
def list_sessions_for_exam(exam_id: int):
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    teacher = current_user()
    err = assert_teacher_owns_exam(exam, teacher.id)
    if err is not None:
        return err

    page, page_size, perr = _get_pagination_params()
    if perr is not None:
        return perr

    items, total = list_exam_sessions(exam, page, page_size)
    return jsonify(_envelope(items, page, page_size, total)), 200


# ---------------------------------------------------------------------------
# GET /sessions/<id>/detail
# ---------------------------------------------------------------------------
@teacher_reports_bp.get("/sessions/<int:session_id>/detail")
@teacher_required
def session_detail(session_id: int):
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    teacher = current_user()
    err = assert_teacher_owns_session(session, teacher.id)
    if err is not None:
        return err

    return jsonify(get_session_detail(session)), 200


# ---------------------------------------------------------------------------
# POST /sessions/<id>/grade
# ---------------------------------------------------------------------------
@teacher_reports_bp.post("/sessions/<int:session_id>/grade")
@teacher_required
def grade_session_endpoint(session_id: int):
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    teacher = current_user()
    err = assert_teacher_owns_session(session, teacher.id)
    if err is not None:
        return err

    payload = request.get_json(silent=True)
    body, gerr = grade_session(session, payload)
    if gerr is not None:
        return gerr
    return jsonify(body), 200


# ---------------------------------------------------------------------------
# GET /exams/<id>/analytics
# ---------------------------------------------------------------------------
@teacher_reports_bp.get("/exams/<int:exam_id>/analytics")
@teacher_required
def exam_analytics(exam_id: int):
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    teacher = current_user()
    err = assert_teacher_owns_exam(exam, teacher.id)
    if err is not None:
        return err

    return jsonify(get_exam_analytics(exam)), 200


__all__ = ["teacher_reports_bp"]

"""Sessions blueprint.

Provides session creation, state transitions, answer management,
auto-grading, and result retrieval for students.
"""

from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Exam
from ..models.exam_session import ExamSession
from ..models.enums import (
    SESSION_STATUS_ABORTED_STEALTH_VM,
    SESSION_STATUS_ABORTED_VM,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_PRE_CHECK,
    SESSION_STATUS_SUBMITTED,
    SessionStatusEnum,
)
from ..services.session_service import (
    get_session_result,
    get_time_remaining,
    get_or_create_session,
    submit_session,
    transition_to_in_progress,
    upsert_answer,
)
from ..utils.auth_decorators import current_user, jwt_required, student_required, teacher_required
from ..utils.responses import error_response, validation_error

sessions_bp = Blueprint("sessions", __name__)


def _serialize_question_for_student(question) -> Dict[str, Any]:
    """Serialize a question for student (no correct_answer)."""
    from ..models.enums import QUESTION_TYPE_MCQ

    data = {
        "id": question.id,
        "question_text": question.prompt,
        "question_type": question.question_type,
        "marks": question.marks,
        "order_index": question.order_index,
    }

    if question.question_type == QUESTION_TYPE_MCQ:
        data["options"] = [
            q for q in [question.option_a, question.option_b, question.option_c, question.option_d] if q
        ]

    return data


# ------------------------------------------------------------------------
# Session creation and lifecycle
# ------------------------------------------------------------------------


@sessions_bp.get("/sessions/me")
@student_required
def list_my_sessions():
    """List the current student's sessions in terminal states (history).

    Returns a paginated list of sessions that are submitted, expired,
    aborted_vm, or aborted_stealth_vm — ordered by ended_at descending.
    """
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 20)), 100)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20

    user = current_user()

    terminal_states = [
        SESSION_STATUS_SUBMITTED,
        SESSION_STATUS_EXPIRED,
        SESSION_STATUS_ABORTED_VM,
        SESSION_STATUS_ABORTED_STEALTH_VM,
    ]

    query = (
        db.session.query(ExamSession)
        .filter(
            ExamSession.student_id == user.id,
            ExamSession.status.in_(terminal_states),
        )
        .order_by(ExamSession.ended_at.desc().nullslast())
    )

    total_items = query.count()
    sessions = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for s in sessions:
        exam = db.session.get(Exam, s.exam_id)
        course = exam.course if exam else None
        items.append({
            "id": s.id,
            "exam_id": s.exam_id,
            "exam_title": exam.title if exam else "Unknown",
            "course_code": course.code if course else "",
            "status": str(s.status),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "score": s.score,
            "total_marks": exam.total_marks if exam else None,
        })

    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    return jsonify({
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    }), 200


@sessions_bp.post("/sessions")
@student_required
def create_session():
    """Create or resume a session (student-only)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    exam_id = payload.get("exam_id")
    if not isinstance(exam_id, int) or exam_id <= 0:
        return validation_error({"exam_id": ["Exam id is required and must be a positive integer."]})

    user = current_user()

    try:
        session = get_or_create_session(exam_id, user.id)
    except Exception as e:
        if isinstance(e, tuple):
            return e  # error_response tuple
        raise

    # Check if the result is an error response tuple
    if isinstance(session, tuple):
        return session

    exam = db.session.get(Exam, session.exam_id)

    # Calculate time_remaining (duration_minutes * 60 since not started yet)
    time_remaining_seconds = exam.duration_minutes * 60 if session.status == SESSION_STATUS_PRE_CHECK else 0

    body = {
        "id": session.id,
        "exam_id": session.exam_id,
        "student_id": session.student_id,
        "status": str(session.status),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "deadline_at": session.deadline_at.isoformat() if session.deadline_at else None,
        "time_remaining_seconds": time_remaining_seconds,
        "questions": [_serialize_question_for_student(q) for q in exam.questions],
    }
    return jsonify(body), 201


@sessions_bp.patch("/sessions/<int:session_id>")
@student_required
def transition_session(session_id: int):
    """Transition session status (student-only, must own session)."""
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    user = current_user()
    if session.student_id != user.id:
        return error_response("forbidden", "You do not own this session.", 403)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    status = payload.get("status")
    if not isinstance(status, str) or not status:
        return validation_error({"status": ["Status is required."]})

    valid_transitions = {
        SESSION_STATUS_PRE_CHECK: [SESSION_STATUS_IN_PROGRESS],
        SESSION_STATUS_IN_PROGRESS: [SESSION_STATUS_SUBMITTED],
    }

    if status not in valid_transitions.get(str(session.status), []):
        return validation_error(
            {"status": ["Invalid status transition for current session state."]}
        )

    # Check if session is already in a terminal state
    if str(session.status) in [
        SESSION_STATUS_SUBMITTED,
        SESSION_STATUS_EXPIRED,
        SESSION_STATUS_ABORTED_VM,
        SESSION_STATUS_ABORTED_STEALTH_VM,
    ]:
        return error_response("conflict", "Session is in a terminal state.", 409)

    # Validate status is a valid enum value
    valid_statuses = [
        SESSION_STATUS_IN_PROGRESS,
        SESSION_STATUS_SUBMITTED,
        SESSION_STATUS_ABORTED_VM,
        SESSION_STATUS_ABORTED_STEALTH_VM,
    ]
    if status not in valid_statuses:
        return validation_error({"status": ["Invalid status value."]})

    # Handle transitions
    if status == SESSION_STATUS_IN_PROGRESS:
        if session.status != SESSION_STATUS_PRE_CHECK:
            return error_response(
                "conflict",
                "Session is not in pre_check state.",
                409,
                details={"code": "invalid_state_transition"},
            )
        session = transition_to_in_progress(session)

    elif status in [SessionStatusEnum.ABORTED_VM, SessionStatusEnum.ABORTED_STEALTH_VM]:
        if session.status != SESSION_STATUS_PRE_CHECK:
            return error_response(
                "conflict",
                "Session is not in pre_check state.",
                409,
                details={"code": "invalid_state_transition"},
            )
        session.status = status
        session.ended_at = None
        db.session.commit()
        db.session.refresh(session)

    elif status == SESSION_STATUS_SUBMITTED:
        # This is handled by POST /sessions/{id}/submit
        return error_response(
            "bad_request",
            "Use POST /sessions/{id}/submit to submit.",
            400,
        )

    body = {
        "id": session.id,
        "exam_id": session.exam_id,
        "student_id": session.student_id,
        "status": str(session.status),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "submitted_at": session.ended_at.isoformat() if session.ended_at else None,
        "deadline_at": session.deadline_at.isoformat() if session.deadline_at else None,
        "time_remaining_seconds": 0,  # Not applicable after transition
    }
    if session.score is not None:
        body["score"] = session.score

    return jsonify(body), 200


# ------------------------------------------------------------------------
# Answer management
# ------------------------------------------------------------------------


@sessions_bp.put("/sessions/<int:session_id>/answers/<int:question_id>")
@student_required
def save_answer(session_id: int, question_id: int):
    """Save or update an answer (student-only, must own session)."""
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    user = current_user()
    if session.student_id != user.id:
        return error_response("forbidden", "You do not own this session.", 403)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    answer_text = payload.get("answer_text")
    if not isinstance(answer_text, str) or not answer_text.strip():
        return validation_error({"answer_text": ["Answer text is required."]})

    if len(answer_text) > 8000:
        return validation_error({"answer_text": ["Answer text must be at most 8000 characters."]})

    try:
        answer = upsert_answer(session, question_id, answer_text.strip())
    except Exception as e:
        if isinstance(e, tuple):
            return e
        raise

    if isinstance(answer, tuple):
        return answer

    body = {
        "id": answer.id,
        "session_id": answer.session_id,
        "question_id": answer.question_id,
        "answer_text": answer.answer_text,
        "saved_at": answer.saved_at.isoformat(),
    }
    return jsonify(body), 200


# ------------------------------------------------------------------------
# Submission and grading
# ------------------------------------------------------------------------


@sessions_bp.post("/sessions/<int:session_id>/submit")
@student_required
def submit_session_endpoint(session_id: int):
    """Submit a session and auto-grade (student-only, must own session)."""
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    user = current_user()
    if session.student_id != user.id:
        return error_response("forbidden", "You do not own this session.", 403)

    result = submit_session(session)

    # submit_session returns an error-response tuple on failure
    if isinstance(result, tuple):
        return result

    body = {
        "id": session.id,
        "exam_id": session.exam_id,
        "status": str(session.status),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "submitted_at": session.ended_at.isoformat() if session.ended_at else None,
        "score": result["score"],
        "total_marks": result["total_marks"],
        "mcq_marks_awarded": result["mcq_marks_awarded"],
        "mcq_marks_possible": result["mcq_marks_possible"],
        "pending_manual_marks": result["pending_manual_marks"],
    }
    return jsonify(body), 200


# ------------------------------------------------------------------------
# Time remaining
# ------------------------------------------------------------------------


@sessions_bp.get("/sessions/<int:session_id>/time")
@student_required
def get_time_endpoint(session_id: int):
    """Get time remaining for a session (student-only, must own session)."""
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    user = current_user()
    if session.student_id != user.id:
        return error_response("forbidden", "You do not own this session.", 403)

    result = get_time_remaining(session)
    return jsonify(result), 200


# ------------------------------------------------------------------------
# Results
# ------------------------------------------------------------------------


@sessions_bp.get("/sessions/<int:session_id>/result")
@jwt_required()
def get_result(session_id: int):
    """Get session result (student must own, or teacher must own exam's course)."""
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return error_response("not_found", "Session not found.", 404)

    user = current_user()

    # Student must own the session
    if user.role == "student":
        if session.student_id != user.id:
            return error_response("forbidden", "You do not own this session.", 403)
    # Teacher must own the exam's course
    else:
        exam = db.session.get(Exam, session.exam_id)
        from ..models import Course
        course = db.session.get(Course, exam.course_id)
        if course.teacher_id != user.id:
            return error_response("forbidden", "You do not own this exam's course.", 403)

    try:
        result = get_session_result(session, user.role)
    except Exception as e:
        if hasattr(e, "get_response"):
            return e.get_response()
        raise

    return jsonify(result), 200


__all__ = ["sessions_bp"]

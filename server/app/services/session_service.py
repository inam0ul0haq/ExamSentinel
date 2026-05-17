"""Service layer for session operations.

Keeps route handlers thin by encapsulating business logic for session
creation, state transitions, answer management, auto-grading, and
time-remaining checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from ..extensions import db
from ..models import Answer, Exam, Question
from ..models.exam_session import ExamSession
from ..models.enums import (
    ENROLLMENT_STATUS_ACTIVE,
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_SHORT_ANSWER,
    SESSION_STATUS_ABORTED_STEALTH_VM,
    SESSION_STATUS_ABORTED_VM,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_PRE_CHECK,
    SESSION_STATUS_SUBMITTED,
    SessionStatusEnum,
)
from ..utils.responses import error_response, validation_error


def validate_session_eligibility(exam: Exam, student_id: int) -> bool:
    """Validate that a student can start a session for an exam.

    Returns True if the student is enrolled in the exam's course.
    """
    from ..models import Enrollment

    enrollment = (
        db.session.query(Enrollment.id)
        .filter(
            Enrollment.student_id == student_id,
            Enrollment.course_id == exam.course_id,
            Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
        )
        .first()
    )
    return bool(enrollment)


def get_or_create_session(exam_id: int, student_id: int) -> ExamSession:
    """Get an existing pre_check or in_progress session, or create a new one.

    Returns the session. Raises errors if:
    - Exam is not active or outside window
    - Student not enrolled
    - Student has a submitted/reviewed session (no retakes)
    """
    exam = db.session.get(Exam, exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)

    now = datetime.now(timezone.utc)

    # Convert start_window to aware datetime if it's naive
    start_window = exam.start_window
    if start_window and start_window.tzinfo is None:
        start_window = start_window.replace(tzinfo=timezone.utc)
    
    # Convert end_window to aware datetime if it's naive
    end_window = exam.end_window
    if end_window and end_window.tzinfo is None:
        end_window = end_window.replace(tzinfo=timezone.utc)

    # Check exam is active and within window
    if not exam.is_active:
        return error_response("forbidden", "Exam is not active.", 403, details={"code": "exam_not_active"})

    if start_window and now < start_window:
        return error_response("forbidden", "Exam window has not opened yet.", 403, details={"code": "exam_window_closed"})

    if end_window and now > end_window:
        return error_response("forbidden", "Exam window has closed.", 403, details={"code": "exam_window_closed"})

    # Check enrollment
    if not validate_session_eligibility(exam, student_id):
        return error_response("forbidden", "You are not enrolled in this exam's course.", 403, details={"code": "not_enrolled"})

    # Check for existing session
    existing_session = (
        db.session.query(ExamSession)
        .filter(
            ExamSession.exam_id == exam_id,
            ExamSession.student_id == student_id,
        )
        .first()
    )

    if existing_session:
        # If pre_check or in_progress, return it (resume semantics)
        if existing_session.status in [SESSION_STATUS_PRE_CHECK, SESSION_STATUS_IN_PROGRESS]:
            return existing_session
        # If submitted or reviewed, no retakes
        elif existing_session.status == SESSION_STATUS_SUBMITTED:
            return error_response("conflict", "You have already attempted this exam.", 409, details={"code": "already_attempted"})
        # If aborted, allow new attempt
        else:
            pass  # Create new session

    # Create new session
    session = ExamSession(
        exam_id=exam_id,
        student_id=student_id,
        status=SESSION_STATUS_PRE_CHECK,
    )
    db.session.add(session)
    db.session.commit()
    db.session.refresh(session)
    return session


def transition_to_in_progress(session: ExamSession) -> ExamSession:
    """Transition a session from pre_check to in_progress.

    Sets started_at and computes deadline_at.
    """
    if session.status != SESSION_STATUS_PRE_CHECK:
        raise error_response(
            "conflict",
            "Session is not in pre_check state.",
            409,
            details={"code": "invalid_state_transition"},
        )

    exam = db.session.get(Exam, session.exam_id)
    now = datetime.now(timezone.utc)

    session.status = SESSION_STATUS_IN_PROGRESS
    session.started_at = now
    session.deadline_at = now + timedelta(minutes=exam.duration_minutes)

    db.session.commit()
    db.session.refresh(session)
    return session


def upsert_answer(session: ExamSession, question_id: int, answer_text: str) -> Answer:
    """Save or update an answer for a question.

    Validates that the session is in_progress and not expired.
    """
    now = datetime.now(timezone.utc)

    # Convert deadline_at to aware datetime if it's naive
    deadline_at = session.deadline_at
    if deadline_at and deadline_at.tzinfo is None:
        deadline_at = deadline_at.replace(tzinfo=timezone.utc)

    if session.status != SESSION_STATUS_IN_PROGRESS:
        raise error_response("bad_request", "Session is not in progress.", 400)

    if deadline_at and now > deadline_at:
        raise error_response("bad_request", "Session has expired.", 400)
            "conflict",
            "Session has expired.",
            409,
            details={"code": "session_expired"},
        )

    question = db.session.get(Question, question_id)
    if question is None or question.exam_id != session.exam_id:
        raise validation_error({"question_id": ["Question not found in this exam."]})

    # For MCQs, validate answer is one of the options
    if question.question_type == QUESTION_TYPE_MCQ:
        options = [q for q in [question.option_a, question.option_b, question.option_c, question.option_d] if q]
        if answer_text not in options:
            raise validation_error({"answer_text": ["Answer must be one of the options."]})

    # Upsert answer
    answer = (
        db.session.query(Answer)
        .filter(
            Answer.session_id == session.id,
            Answer.question_id == question_id,
        )
        .first()
    )

    if answer:
        answer.answer_text = answer_text
        answer.is_auto_graded = False
    else:
        answer = Answer(
            session_id=session.id,
            question_id=question_id,
            answer_text=answer_text,
        )
        db.session.add(answer)

    db.session.commit()
    db.session.refresh(answer)
    return answer


def submit_session(session: ExamSession) -> Dict[str, Any]:
    """Submit a session and auto-grade MCQ answers.

    Returns the score breakdown.
    """
    if session.status != SESSION_STATUS_IN_PROGRESS:
        raise error_response(
            "conflict",
            "Session is not in progress.",
            409,
        )

    now = datetime.now(timezone.utc)
    session.status = SESSION_STATUS_SUBMITTED
    session.ended_at = now

    # Auto-grade MCQ answers
    exam = db.session.get(Exam, session.exam_id)
    questions = exam.questions

    total_mcq_marks = 0
    mcq_marks_awarded = 0
    pending_manual_marks = 0

    for question in questions:
        answer = (
            db.session.query(Answer)
            .filter(
                Answer.session_id == session.id,
                Answer.question_id == question.id,
            )
            .first()
        )

        if question.question_type == QUESTION_TYPE_MCQ:
            total_mcq_marks += question.marks
            if answer and answer.answer_text == question.correct_option:
                answer.marks_awarded = question.marks
                answer.is_auto_graded = True
                mcq_marks_awarded += question.marks
            elif answer:
                answer.marks_awarded = 0
                answer.is_auto_graded = True
        else:
            # Short answer - pending manual grading
            pending_manual_marks += question.marks

    session.score = float(mcq_marks_awarded)

    db.session.commit()
    db.session.refresh(session)

    return {
        "score": session.score,
        "total_marks": exam.total_marks,
        "mcq_marks_awarded": mcq_marks_awarded,
        "mcq_marks_possible": total_mcq_marks,
        "pending_manual_marks": pending_manual_marks,
    }

def get_time_remaining(session: ExamSession) -> Dict[str, Any]:
    """Get time remaining for a session.

    Auto-expires session if deadline has passed.
    """
    now = datetime.now(timezone.utc)

    # Convert deadline_at to aware datetime if it's naive
    deadline_at = session.deadline_at
    if deadline_at and deadline_at.tzinfo is None:
        deadline_at = deadline_at.replace(tzinfo=timezone.utc)

    if session.status != SESSION_STATUS_SUBMITTED:
        time_remaining = (deadline_at - now).total_seconds() if deadline_at else 0

        # Auto-expire if deadline passed
        if time_remaining <= 0:
            session.status = SESSION_STATUS_EXPIRED
            session.ended_at = now
            db.session.commit()
            db.session.refresh(session)
            return {
                "server_time": now.isoformat(),
                "deadline_at": session.deadline_at.isoformat() if session.deadline_at else None,
                "time_remaining_seconds": 0,
                "expired": True,
            }

        return {
            "server_time": now.isoformat(),
            "deadline_at": session.deadline_at.isoformat() if session.deadline_at else None,
            "time_remaining_seconds": int(time_remaining),
            "expired": False,
        }

    # Submitted sessions show as expired
    return {
        "time_remaining_seconds": 0,
        "expired": True,
    }


def get_session_result(session: ExamSession, user_role: str) -> Dict[str, Any]:
    """Get the result for a session.

    For students, omits correct_answer. For teachers, includes it.
    """
    if session.status != SESSION_STATUS_SUBMITTED:
        return error_response("bad_request", "Session must be submitted to get results.", 400)

    exam = db.session.get(Exam, session.exam_id)
    questions = exam.questions

    # Calculate totals
    total_mcq_marks = sum(q.marks for q in questions if q.question_type == QUESTION_TYPE_MCQ)
    pending_manual_marks = sum(q.marks for q in questions if q.question_type == QUESTION_TYPE_SHORT_ANSWER)

    breakdown = []
    for question in questions:
        answer = (
            db.session.query(Answer)
            .filter(
                Answer.session_id == session.id,
                Answer.question_id == question.id,
            )
            .first()
        )

        item = {
            "question_id": question.id,
            "question_text": question.prompt,
            "question_type": question.question_type,
            "marks": question.marks,
            "answer_text": answer.answer_text if answer else None,
            "marks_awarded": answer.marks_awarded if answer else None,
        }

        if question.question_type == QUESTION_TYPE_MCQ:
            item["options"] = [
                q for q in [question.option_a, question.option_b, question.option_c, question.option_d] if q
            ]
            item["is_correct"] = answer.answer_text == question.correct_option if answer else None
            # Only include correct_answer for teachers
            if user_role == "teacher":
                item["correct_answer"] = question.correct_option
        else:
            item["options"] = None
            item["is_correct"] = None

        breakdown.append(item)

    return {
        "id": session.id,
        "exam_id": exam.id,
        "exam_title": exam.title,
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "submitted_at": session.ended_at.isoformat() if session.ended_at else None,
        "score": session.score,
        "total_marks": exam.total_marks,
        "mcq_marks_awarded": sum(
            a.marks_awarded or 0
            for q in questions
            if q.question_type == QUESTION_TYPE_MCQ
            for a in [db.session.query(Answer).filter(
                Answer.session_id == session.id,
                Answer.question_id == q.id,
            ).first()]
            if a
        ),
        "mcq_marks_possible": total_mcq_marks,
        "pending_manual_marks": pending_manual_marks,
        "breakdown": breakdown,
    }


__all__ = [
    "validate_session_eligibility",
    "get_or_create_session",
    "transition_to_in_progress",
    "upsert_answer",
    "submit_session",
    "get_time_remaining",
    "get_session_result",
]

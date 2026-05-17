"""Service layer for teacher reporting endpoints.

All functions in this module assume the caller is a teacher; the route
handlers enforce role and ownership before delegating here.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from ..extensions import db
from ..models import Answer, Course, Exam, IncidentLog, Question, Student
from ..models.enums import (
    INCIDENT_SEVERITY_CRITICAL,
    INCIDENT_SEVERITY_INFO,
    INCIDENT_SEVERITY_VALUES,
    INCIDENT_SEVERITY_WARNING,
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_SHORT_ANSWER,
    SESSION_STATUS_SUBMITTED,
)
from ..models.exam_session import ExamSession
from ..models.user import User
from ..utils.responses import error_response, validation_error


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_SEVERITY_RANK = {
    INCIDENT_SEVERITY_INFO: 1,
    INCIDENT_SEVERITY_WARNING: 2,
    INCIDENT_SEVERITY_CRITICAL: 3,
}


def _highest_severity(severities: List[str]) -> Optional[str]:
    if not severities:
        return None
    return max(severities, key=lambda s: _SEVERITY_RANK.get(s, 0))


def assert_teacher_owns_exam(
    exam: Exam, teacher_id: int
) -> Optional[Tuple]:
    """Return error tuple if the teacher does not own the exam's course."""
    course = db.session.get(Course, exam.course_id)
    if course is None or course.teacher_id != teacher_id:
        return error_response(
            "forbidden",
            "You do not own this exam.",
            403,
        )
    return None


def assert_teacher_owns_session(
    session: ExamSession, teacher_id: int
) -> Optional[Tuple]:
    """Return error tuple if the teacher does not own the session's exam."""
    exam = db.session.get(Exam, session.exam_id)
    if exam is None:
        return error_response("not_found", "Exam not found.", 404)
    return assert_teacher_owns_exam(exam, teacher_id)


# ---------------------------------------------------------------------------
# Exam sessions list (with incident counts and highest severity)
# ---------------------------------------------------------------------------
def list_exam_sessions(
    exam: Exam,
    page: int,
    page_size: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return ``(items, total_items)``."""
    base_query = (
        db.session.query(ExamSession)
        .filter(ExamSession.exam_id == exam.id)
        .order_by(ExamSession.id.desc())
    )
    total_items = base_query.count()
    rows = base_query.offset((page - 1) * page_size).limit(page_size).all()

    if not rows:
        return [], total_items

    session_ids = [s.id for s in rows]

    # Incident counts per session
    count_rows = (
        db.session.query(
            IncidentLog.session_id,
            func.count(IncidentLog.id),
        )
        .filter(IncidentLog.session_id.in_(session_ids))
        .group_by(IncidentLog.session_id)
        .all()
    )
    incident_counts: Dict[int, int] = {sid: cnt for sid, cnt in count_rows}

    # Severities per session (cheap lookup; sessions are few)
    severity_rows = (
        db.session.query(IncidentLog.session_id, IncidentLog.severity)
        .filter(IncidentLog.session_id.in_(session_ids))
        .all()
    )
    sev_by_session: Dict[int, List[str]] = {}
    for sid, sev in severity_rows:
        sev_by_session.setdefault(sid, []).append(sev)

    items: List[Dict[str, Any]] = []
    for session in rows:
        student = db.session.get(Student, session.student_id)
        items.append({
            "id": session.id,
            "student": {
                "id": student.id if student else None,
                "name": student.full_name if student else None,
                "roll_number": student.roll_number if student else None,
            } if student else None,
            "status": session.status,
            "started_at": (
                session.started_at.isoformat()
                if session.started_at else None
            ),
            "ended_at": (
                session.ended_at.isoformat()
                if session.ended_at else None
            ),
            "score": session.score,
            "total_marks": exam.total_marks,
            "incident_count": incident_counts.get(session.id, 0),
            "highest_incident_severity": _highest_severity(
                sev_by_session.get(session.id, [])
            ),
        })

    return items, total_items


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------
def get_session_detail(session: ExamSession) -> Dict[str, Any]:
    exam = db.session.get(Exam, session.exam_id)
    course = db.session.get(Course, exam.course_id) if exam else None
    student = db.session.get(Student, session.student_id)

    # Questions with answers
    questions = (
        db.session.query(Question)
        .filter(Question.exam_id == exam.id)
        .order_by(Question.order_index.asc())
        .all()
    )
    answers_by_q = {
        a.question_id: a
        for a in (
            db.session.query(Answer)
            .filter(Answer.session_id == session.id)
            .all()
        )
    }

    question_items: List[Dict[str, Any]] = []
    for q in questions:
        ans = answers_by_q.get(q.id)
        item: Dict[str, Any] = {
            "id": q.id,
            "question_text": q.prompt,
            "question_type": q.question_type,
            "marks": q.marks,
            "order_index": q.order_index,
            "answer_text": ans.answer_text if ans else None,
            "marks_awarded": ans.marks_awarded if ans else None,
            "is_auto_graded": (ans.is_auto_graded if ans else None),
        }
        if q.question_type == QUESTION_TYPE_MCQ:
            item["options"] = [
                opt for opt in (q.option_a, q.option_b, q.option_c, q.option_d)
                if opt
            ]
            # Teacher view: include the correct option letter
            item["correct_option"] = q.correct_option
        question_items.append(item)

    # Incident log ordered by occurred_at + aggregates
    incidents = (
        db.session.query(IncidentLog)
        .filter(IncidentLog.session_id == session.id)
        .order_by(IncidentLog.occurred_at.asc(), IncidentLog.id.asc())
        .all()
    )
    incident_items = [{
        "id": inc.id,
        "type": inc.incident_type,
        "severity": inc.severity,
        "description": inc.description,
        "cpu_thermal_value": inc.cpu_thermal_value,
        "timing_latency_ms": inc.timing_latency_ms,
        "evidence_path": inc.evidence_path,
        "occurred_at": (
            inc.occurred_at.isoformat() if inc.occurred_at else None
        ),
    } for inc in incidents]

    by_type = Counter(inc.incident_type for inc in incidents)

    return {
        "id": session.id,
        "status": session.status,
        "started_at": (
            session.started_at.isoformat() if session.started_at else None
        ),
        "ended_at": (
            session.ended_at.isoformat() if session.ended_at else None
        ),
        "deadline_at": (
            session.deadline_at.isoformat() if session.deadline_at else None
        ),
        "score": session.score,
        "total_marks": exam.total_marks if exam else None,
        "exam": {
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "is_active": exam.is_active,
            "course_id": course.id if course else None,
            "course_title": course.title if course else None,
            "course_code": course.code if course else None,
        } if exam else None,
        "student": {
            "id": student.id,
            "name": student.full_name,
            "email": student.email,
            "roll_number": student.roll_number,
            "department_id": student.department_id,
            "semester": student.semester,
        } if student else None,
        "questions": question_items,
        "incidents": incident_items,
        "incident_counts": {
            "total": len(incidents),
            "by_type": dict(by_type),
            "by_severity": {
                sev: sum(1 for i in incidents if i.severity == sev)
                for sev in INCIDENT_SEVERITY_VALUES
            },
        },
    }


# ---------------------------------------------------------------------------
# Manual grading
# ---------------------------------------------------------------------------
def grade_session(
    session: ExamSession,
    payload: Any,
) -> Tuple[Dict[str, Any], Optional[Tuple]]:
    if not isinstance(payload, dict):
        return {}, error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )
    items = payload.get("grades")
    if not isinstance(items, list) or not items:
        return {}, validation_error(
            {"grades": ["Field must be a non-empty list."]}
        )

    # Build a quick lookup of the exam's questions by id.
    questions = {
        q.id: q
        for q in (
            db.session.query(Question)
            .filter(Question.exam_id == session.exam_id)
            .all()
        )
    }

    field_errors: Dict[str, List[str]] = {}
    cleaned: List[Tuple[int, float]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            field_errors[f"grades.{idx}._"] = ["Grade entry must be an object."]
            continue
        qid = item.get("question_id")
        marks = item.get("marks_awarded")
        if not isinstance(qid, int) or qid <= 0:
            field_errors[f"grades.{idx}.question_id"] = [
                "question_id is required."
            ]
            continue
        if qid not in questions:
            field_errors[f"grades.{idx}.question_id"] = [
                "Question is not part of this session's exam."
            ]
            continue
        q = questions[qid]
        if q.question_type != QUESTION_TYPE_SHORT_ANSWER:
            field_errors[f"grades.{idx}.question_id"] = [
                "Only short_answer questions can be manually graded."
            ]
            continue
        try:
            marks_f = float(marks)
        except (TypeError, ValueError):
            field_errors[f"grades.{idx}.marks_awarded"] = [
                "marks_awarded must be a number."
            ]
            continue
        if marks_f < 0 or marks_f > q.marks:
            field_errors[f"grades.{idx}.marks_awarded"] = [
                f"marks_awarded must be between 0 and {q.marks}."
            ]
            continue
        cleaned.append((qid, marks_f))

    if field_errors:
        return {}, validation_error(field_errors)

    # Apply: upsert Answer rows so a grade can be set even if the
    # student never saved an answer.
    for qid, marks_f in cleaned:
        answer = (
            db.session.query(Answer)
            .filter(
                Answer.session_id == session.id,
                Answer.question_id == qid,
            )
            .first()
        )
        if answer is None:
            answer = Answer(
                session_id=session.id,
                question_id=qid,
                answer_text=None,
                marks_awarded=marks_f,
                is_auto_graded=False,
            )
            db.session.add(answer)
        else:
            answer.marks_awarded = marks_f
            answer.is_auto_graded = False

    db.session.flush()

    # Recompute session score: sum of marks_awarded across every answer.
    total_awarded = (
        db.session.query(func.coalesce(func.sum(Answer.marks_awarded), 0.0))
        .filter(Answer.session_id == session.id)
        .scalar()
    )
    session.score = float(total_awarded or 0.0)

    db.session.commit()
    db.session.refresh(session)

    exam = db.session.get(Exam, session.exam_id)
    return {
        "session_id": session.id,
        "score": session.score,
        "total_marks": exam.total_marks if exam else None,
        "graded_count": len(cleaned),
    }, None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def get_exam_analytics(exam: Exam) -> Dict[str, Any]:
    sessions = (
        db.session.query(ExamSession)
        .filter(ExamSession.exam_id == exam.id)
        .all()
    )

    status_counts: Counter = Counter(s.status for s in sessions)
    submitted = [s for s in sessions if s.status == SESSION_STATUS_SUBMITTED]
    scores = [
        float(s.score) for s in submitted if s.score is not None
    ]

    if scores:
        mean_score = sum(scores) / len(scores)
        median_score = statistics.median(scores)
        min_score = min(scores)
        max_score = max(scores)
    else:
        mean_score = median_score = min_score = max_score = None

    # Incidents (only for sessions of this exam)
    session_ids = [s.id for s in sessions]
    incidents: List[IncidentLog] = []
    if session_ids:
        incidents = (
            db.session.query(IncidentLog)
            .filter(IncidentLog.session_id.in_(session_ids))
            .all()
        )

    by_type = Counter(inc.incident_type for inc in incidents)
    top_types = [
        {"type": t, "count": c}
        for t, c in by_type.most_common(5)
    ]

    # Percent of submitted sessions with at least one critical incident.
    critical_session_ids = {
        inc.session_id for inc in incidents
        if inc.severity == INCIDENT_SEVERITY_CRITICAL
    }
    submitted_ids = {s.id for s in submitted}
    crit_in_submitted = len(critical_session_ids & submitted_ids)
    pct_submitted_critical = (
        (crit_in_submitted / len(submitted)) * 100.0
        if submitted else 0.0
    )

    return {
        "exam_id": exam.id,
        "title": exam.title,
        "is_active": exam.is_active,
        "total_marks": exam.total_marks,
        "sessions_by_status": dict(status_counts),
        "submitted_count": len(submitted),
        "score_stats": {
            "mean": mean_score,
            "median": median_score,
            "min": min_score,
            "max": max_score,
        },
        "incidents": {
            "total": len(incidents),
            "top_types": top_types,
            "percent_submitted_with_critical": round(
                pct_submitted_critical, 2
            ),
        },
    }


__all__ = [
    "assert_teacher_owns_exam",
    "assert_teacher_owns_session",
    "list_exam_sessions",
    "get_session_detail",
    "grade_session",
    "get_exam_analytics",
]

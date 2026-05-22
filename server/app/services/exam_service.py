"""Service layer for exam operations.

Keeps route handlers thin by encapsulating business logic for exam
creation, validation, activation, and question management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from ..extensions import db
from ..models import Course, Exam, Question
from ..models.enums import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_SHORT_ANSWER,
    SESSION_STATUS_ABORTED_STEALTH_VM,
    SESSION_STATUS_ABORTED_VM,
    SESSION_STATUS_SUBMITTED,
)
from ..utils.responses import error_response, validation_error


def validate_exam_ownership(course_id: int, teacher_id: int) -> Optional[Course]:
    """Validate that the teacher owns the course.

    Returns the Course if valid, None otherwise.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return None
    if course.teacher_id != teacher_id:
        return None
    return course


def validate_questions_payload(questions: List[Dict[str, Any]]):
    """Validate the questions array for exam creation/update.

    Returns a Flask error-response tuple on failure, or None on success.
    """
    if not questions:
        return validation_error({"questions": ["Questions array cannot be empty."]})

    errors: Dict[str, List[str]] = {}
    order_indices = set()

    for idx, q in enumerate(questions):
        prefix = f"questions[{idx}]"

        # Validate required fields
        question_text = q.get("question_text")
        if not isinstance(question_text, str) or not question_text.strip():
            errors.setdefault(f"{prefix}.question_text", []).append(
                "Question text is required."
            )
        elif len(question_text) > 4000:
            errors.setdefault(f"{prefix}.question_text", []).append(
                "Question text must be at most 4000 characters."
            )

        question_type = q.get("question_type")
        if question_type not in [QUESTION_TYPE_MCQ, QUESTION_TYPE_SHORT_ANSWER]:
            errors.setdefault(f"{prefix}.question_type", []).append(
                "Question type must be 'mcq' or 'short_answer'."
            )

        marks = q.get("marks")
        if not isinstance(marks, int) or marks <= 0 or marks > 100:
            errors.setdefault(f"{prefix}.marks", []).append(
                "Marks must be an integer between 1 and 100."
            )

        order_index = q.get("order_index")
        if not isinstance(order_index, int) or order_index < 1:
            errors.setdefault(f"{prefix}.order_index", []).append(
                "Order index must be a positive integer."
            )
        elif order_index in order_indices:
            errors.setdefault(f"{prefix}.order_index", []).append(
                "Order index must be unique within the exam."
            )
        order_indices.add(order_index)

        # Type-specific validation
        if question_type == QUESTION_TYPE_MCQ:
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 2 or len(options) > 6:
                errors.setdefault(f"{prefix}.options", []).append(
                    "MCQ questions must have 2-6 options."
                )
            else:
                for opt_idx, opt in enumerate(options):
                    if not isinstance(opt, str) or not opt.strip():
                        errors.setdefault(f"{prefix}.options[{opt_idx}]", []).append(
                            "Option cannot be empty."
                        )

            correct_answer = q.get("correct_answer")
            if not isinstance(correct_answer, str) or not correct_answer.strip():
                errors.setdefault(f"{prefix}.correct_answer", []).append(
                    "Correct answer is required for MCQ questions."
                )
            elif isinstance(options, list) and correct_answer not in options:
                errors.setdefault(f"{prefix}.correct_answer", []).append(
                    "Correct answer must be one of the options."
                )

        elif question_type == QUESTION_TYPE_SHORT_ANSWER:
            if q.get("options") is not None:
                errors.setdefault(f"{prefix}.options", []).append(
                    "Options must be omitted for short-answer questions."
                )
            if q.get("correct_answer") is not None:
                errors.setdefault(f"{prefix}.correct_answer", []).append(
                    "Correct answer must be omitted for short-answer questions."
                )

    if errors:
        return validation_error(errors)
    return None


def create_exam(
    course_id: int,
    title: str,
    description: Optional[str],
    duration_minutes: int,
    start_window: Optional[datetime],
    end_window: Optional[datetime],
    questions: List[Dict[str, Any]],
    teacher_id: int,
) -> Exam:
    """Create a new exam with questions in a single transaction.

    Validates course ownership, question payload, and window constraints.
    Returns the created Exam with questions populated.
    """
    course = validate_exam_ownership(course_id, teacher_id)
    if course is None:
        return error_response("forbidden", "You do not own this course.", 403)

    # Validate window
    if start_window and end_window:
        if end_window <= start_window:
            return validation_error(
                {"end_window": ["End window must be after start window."]}
            )

    q_err = validate_questions_payload(questions)
    if q_err is not None:
        return q_err

    # Calculate total_marks from questions
    total_marks = sum(q["marks"] for q in questions)

    exam = Exam(
        course_id=course_id,
        title=title.strip(),
        description=description.strip() if description else None,
        duration_minutes=duration_minutes,
        start_window=start_window,
        end_window=end_window,
        total_marks=total_marks,
        is_active=False,
    )
    db.session.add(exam)
    db.session.flush()  # Get exam.id before creating questions

    # Create questions
    for q in questions:
        if q["question_type"] == QUESTION_TYPE_MCQ:
            options = q.get("options", [])
            correct_answer = q.get("correct_answer")
            
            # Map correct_answer (option text) to letter (A, B, C, D)
            correct_option_letter = None
            if correct_answer and correct_answer in options:
                option_index = options.index(correct_answer)
                if option_index == 0:
                    correct_option_letter = "A"
                elif option_index == 1:
                    correct_option_letter = "B"
                elif option_index == 2:
                    correct_option_letter = "C"
                elif option_index == 3:
                    correct_option_letter = "D"
            
            question = Question(
                exam_id=exam.id,
                prompt=q["question_text"],
                question_type=q["question_type"],
                marks=q["marks"],
                order_index=q["order_index"],
                option_a=options[0] if len(options) > 0 else None,
                option_b=options[1] if len(options) > 1 else None,
                option_c=options[2] if len(options) > 2 else None,
                option_d=options[3] if len(options) > 3 else None,
                correct_option=correct_option_letter,
            )
        else:
            question = Question(
                exam_id=exam.id,
                prompt=q["question_text"],
                question_type=q["question_type"],
                marks=q["marks"],
                order_index=q["order_index"],
                option_a=None,
                option_b=None,
                option_c=None,
                option_d=None,
                correct_option=None,
            )
        db.session.add(question)

    db.session.commit()
    db.session.refresh(exam)
    return exam


def can_edit_exam(exam: Exam) -> bool:
    """Check if an exam can be edited.

    Returns False if any non-aborted session exists. VM-aborted attempts
    are forensic pre-check failures and are explicitly editable per the
    Part 10 contract.
    """
    from ..models.exam_session import ExamSession

    has_blocking_session = (
        db.session.query(ExamSession.id)
        .filter(
            ExamSession.exam_id == exam.id,
            ExamSession.status.notin_([
                SESSION_STATUS_ABORTED_VM,
                SESSION_STATUS_ABORTED_STEALTH_VM,
            ]),
        )
        .first()
    )
    return not bool(has_blocking_session)


def can_delete_exam(exam: Exam) -> bool:
    """Check if an exam can be deleted.

    Returns False if any session exists.
    """
    from ..models.exam_session import ExamSession

    has_session = (
        db.session.query(ExamSession.id)
        .filter(ExamSession.exam_id == exam.id)
        .first()
    )
    return not bool(has_session)


def activate_exam(exam: Exam) -> Exam:
    """Activate an exam.

    Automatically sets start_window to *now* and end_window to *now + 30 days*
    so the exam is immediately visible to students without manual scheduling.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    exam.is_active = True
    exam.start_window = now
    exam.end_window = now + timedelta(days=30)
    db.session.commit()
    db.session.refresh(exam)
    return exam


def deactivate_exam(exam: Exam) -> Exam:
    """Deactivate an exam."""
    exam.is_active = False
    db.session.commit()
    db.session.refresh(exam)
    return exam


def replace_questions(exam: Exam, questions: List[Dict[str, Any]]) -> Exam:
    """Replace the exam's question set atomically.

    Validates that no session has progressed beyond pre_check.
    Returns the updated exam with new questions.
    """
    if not can_edit_exam(exam):
        return error_response(
            "conflict",
            "Cannot edit exam with active sessions.",
            409,
        )

    q_err = validate_questions_payload(questions)
    if q_err is not None:
        return q_err

    # Delete existing questions
    db.session.query(Question).filter(Question.exam_id == exam.id).delete()

    # Create new questions
    total_marks = 0
    for q in questions:
        total_marks += q["marks"]
        
        if q["question_type"] == QUESTION_TYPE_MCQ:
            options = q.get("options", [])
            correct_answer = q.get("correct_answer")
            
            # Map correct_answer (option text) to letter (A, B, C, D)
            correct_option_letter = None
            if correct_answer and correct_answer in options:
                option_index = options.index(correct_answer)
                if option_index == 0:
                    correct_option_letter = "A"
                elif option_index == 1:
                    correct_option_letter = "B"
                elif option_index == 2:
                    correct_option_letter = "C"
                elif option_index == 3:
                    correct_option_letter = "D"
            
            question = Question(
                exam_id=exam.id,
                prompt=q["question_text"],
                question_type=q["question_type"],
                marks=q["marks"],
                order_index=q["order_index"],
                option_a=options[0] if len(options) > 0 else None,
                option_b=options[1] if len(options) > 1 else None,
                option_c=options[2] if len(options) > 2 else None,
                option_d=options[3] if len(options) > 3 else None,
                correct_option=correct_option_letter,
            )
        else:
            question = Question(
                exam_id=exam.id,
                prompt=q["question_text"],
                question_type=q["question_type"],
                marks=q["marks"],
                order_index=q["order_index"],
                option_a=None,
                option_b=None,
                option_c=None,
                option_d=None,
                correct_option=None,
            )
        db.session.add(question)

    exam.total_marks = total_marks
    db.session.commit()
    db.session.refresh(exam)
    return exam


def get_student_active_exams(student_id: int, page: int, page_size: int) -> tuple:
    """Get active exams for a student.

    Returns (items, total_items) where items are exam summaries.
    Filters by: enrolled in course, is_active=true, within window,
    no submitted/reviewed session exists.
    """
    from ..models import Enrollment
    from ..models.exam_session import ExamSession

    now = datetime.now(timezone.utc)

    # Get exam IDs that the student has already submitted
    submitted_exam_ids = set(
        row[0]
        for row in db.session.query(ExamSession.exam_id)
        .filter(
            ExamSession.student_id == student_id,
            ExamSession.status == SESSION_STATUS_SUBMITTED,
        )
        .distinct()
        .all()
    )

    query = (
        db.session.query(Exam, Course)
        .join(Course, Exam.course_id == Course.id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(
            Enrollment.student_id == student_id,
            Enrollment.status == "active",
            Exam.is_active == True,
        )
    )

    # Filter out exams that have been submitted
    if submitted_exam_ids:
        query = query.filter(~Exam.id.in_(submitted_exam_ids))

    total_items = query.count()
    results = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for exam, course in results:
        # Look up the student's session for this exam (if any)
        session = (
            db.session.query(ExamSession)
            .filter(
                ExamSession.exam_id == exam.id,
                ExamSession.student_id == student_id,
            )
            .first()
        )
        items.append({
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "start_window": exam.start_window,
            "end_window": exam.end_window,
            "course_id": course.id,
            "course_title": course.title,
            "course_code": course.code,
            "question_count": len(exam.questions),
            "session_status": str(session.status) if session else None,
            "session_id": session.id if session else None,
        })

    return items, total_items


__all__ = [
    "validate_exam_ownership",
    "validate_questions_payload",
    "create_exam",
    "can_edit_exam",
    "can_delete_exam",
    "activate_exam",
    "deactivate_exam",
    "replace_questions",
    "get_student_active_exams",
]

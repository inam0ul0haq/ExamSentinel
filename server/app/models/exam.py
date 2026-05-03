"""Exam entity.

An Exam belongs to exactly one Course and is composed of one or more
Questions. ``total_marks`` is a cached integer that the service layer
keeps in sync with ``sum(question.marks)`` whenever the question set
changes; storing it lets list endpoints avoid an aggregate join.

``start_window`` and ``end_window`` together define the calendar
interval in which the exam is accessible to enrolled students (see
``docs/API.md`` §5). The user prompt's "scheduled start time" is
modelled as ``start_window``; ``end_window`` is required by the API
contract for active-window enforcement.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)

from ..extensions import db


class Exam(db.Model):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True)
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    # Optional long description. Capped at 4000 chars per the API
    # contract for exam creation.
    description = Column(String(4000), nullable=True)
    duration_minutes = Column(Integer, nullable=False)

    # Scheduling window. Both nullable so a teacher can author an exam
    # without committing to a date; the server enforces the window only
    # when both are populated.
    start_window = Column(DateTime(timezone=True), nullable=True)
    end_window = Column(DateTime(timezone=True), nullable=True)

    # Cached sum of ``Question.marks`` across all questions on this exam.
    # Service layer recomputes whenever questions are added / removed /
    # mutated.
    total_marks = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # --- Relationships ----------------------------------------------------
    course = db.relationship("Course", back_populates="exams")
    questions = db.relationship(
        "Question",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Question.order_index",
    )
    sessions = db.relationship(
        "ExamSession",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Exam id={self.id} course_id={self.course_id} "
            f"title={self.title!r} is_active={self.is_active}>"
        )


__all__ = ["Exam"]

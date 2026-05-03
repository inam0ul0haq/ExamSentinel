"""ExamSession entity — one student's single attempt at one exam.

The lifecycle states match the user prompt's enumeration:
``pre_check``, ``in_progress``, ``submitted``, ``expired``,
``aborted_vm``, ``aborted_stealth_vm``. Service-layer code is
responsible for validating transitions; the model only enforces the
allowed value set via the SQLAlchemy enum.

``deadline_at`` is server-authoritative: the service layer computes it
when the session leaves ``pre_check`` (deadline = ``started_at`` +
``Exam.duration_minutes``) and the timer endpoint renders it back to
the client without trusting the client's clock.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
)

from ..extensions import db
from .enums import SESSION_STATUS_PRE_CHECK, SessionStatusEnum


class ExamSession(db.Model):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True)
    exam_id = Column(
        Integer,
        ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(
        Integer,
        ForeignKey("students.id"),
        nullable=False,
    )

    status = Column(
        SessionStatusEnum,
        nullable=False,
        default=SESSION_STATUS_PRE_CHECK,
        index=True,
    )

    # Nullable until the session leaves ``pre_check``.
    started_at = Column(DateTime(timezone=True), nullable=True)
    # Nullable until the session reaches a terminal state.
    ended_at = Column(DateTime(timezone=True), nullable=True)
    # Computed at ``in_progress`` transition; nullable for ``pre_check``.
    deadline_at = Column(DateTime(timezone=True), nullable=True)

    # Final score; null until the session is auto-graded on submission.
    score = Column(Float, nullable=True)

    __table_args__ = (
        # Composite lookup index — most session queries filter by both.
        Index("ix_exam_sessions_student_exam", "student_id", "exam_id"),
    )

    # --- Relationships ----------------------------------------------------
    exam = db.relationship("Exam", back_populates="sessions")
    student = db.relationship("Student", back_populates="sessions")
    answers = db.relationship(
        "Answer",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incidents = db.relationship(
        "IncidentLog",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IncidentLog.occurred_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<ExamSession id={self.id} exam_id={self.exam_id} "
            f"student_id={self.student_id} status={self.status!r}>"
        )


__all__ = ["ExamSession"]

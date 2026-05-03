"""Enrollment join entity between Student and Course.

A Student may enrol in many Courses; each pairing is a separate row in
``enrollments``. The composite uniqueness on ``(student_id, course_id)``
prevents duplicate active enrollments. Drops are modelled by flipping
``status`` to ``dropped`` rather than deleting the row, so audit trails
survive (see ``docs/API.md`` §4 ``DELETE /courses/{id}/enrollments``).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)

from ..extensions import db
from .enums import ENROLLMENT_STATUS_ACTIVE, EnrollmentStatusEnum


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True)
    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enrolled_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status = Column(
        EnrollmentStatusEnum,
        nullable=False,
        default=ENROLLMENT_STATUS_ACTIVE,
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            name="uq_enrollments_student_course",
        ),
    )

    # --- Relationships ----------------------------------------------------
    student = db.relationship("Student", back_populates="enrollments")
    course = db.relationship("Course", back_populates="enrollments")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Enrollment id={self.id} student_id={self.student_id} "
            f"course_id={self.course_id} status={self.status!r}>"
        )


__all__ = ["Enrollment"]

"""Course entity.

A Course is owned by exactly one Teacher and contains zero or more
Exams. Students access Courses through Enrollment rows (see
:mod:`.enrollment`).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)

from ..extensions import db


class Course(db.Model):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    # Short stable identifier (e.g. "CS201"). Globally unique across all
    # courses; surfaced in URLs and exports.
    code = Column(String(20), nullable=False, unique=True, index=True)
    title = Column(String(120), nullable=False)
    # Optional long description. Capped at 2000 chars to match the API
    # contract (see ``docs/API.md`` §4 ``POST /courses``).
    description = Column(String(2000), nullable=True)

    teacher_id = Column(
        Integer,
        ForeignKey("teachers.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # --- Relationships ----------------------------------------------------
    teacher = db.relationship("Teacher", back_populates="courses")
    enrollments = db.relationship(
        "Enrollment",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    exams = db.relationship(
        "Exam",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Course id={self.id} code={self.code!r} title={self.title!r}>"


__all__ = ["Course"]

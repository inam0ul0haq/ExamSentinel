"""Teacher entity — joined-table subclass of :class:`User`.

A Teacher owns Courses, authors Exams and Questions, and reviews
sessions. Like :class:`Student`, the FK to ``users.id`` carries no
``ondelete`` cascade so the User row is protected from hard-deletion.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String

from ..extensions import db
from .enums import USER_ROLE_TEACHER
from .user import User


class Teacher(User):
    __tablename__ = "teachers"

    id = Column(
        Integer,
        ForeignKey("users.id"),  # no ondelete — see module docstring
        primary_key=True,
    )
    employee_code = Column(String(32), nullable=False, unique=True, index=True)
    # Free-form rank/title (e.g. "Assistant Professor"). Optional.
    designation = Column(String(80), nullable=True)
    # Optional at registration time — teachers without a department on
    # their account record are allowed; a teacher can be assigned to a
    # department later via the admin tooling that lands in a future part.
    # The FK still points at ``departments.id`` so any non-null value is
    # validated by the database.
    department_id = Column(
        Integer,
        ForeignKey("departments.id"),
        nullable=True,
        index=True,
    )

    # --- Relationships ----------------------------------------------------
    department = db.relationship("Department", back_populates="teachers")
    courses = db.relationship(
        "Course",
        back_populates="teacher",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __mapper_args__ = {
        "polymorphic_identity": USER_ROLE_TEACHER,
    }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Teacher id={self.id} employee_code={self.employee_code!r} "
            f"department_id={self.department_id}>"
        )


__all__ = ["Teacher"]

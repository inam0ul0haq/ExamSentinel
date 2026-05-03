"""Student entity — joined-table subclass of :class:`User`.

A Student row shares its primary key with its parent User row. The FK
deliberately has **no** ``ondelete`` cascade so a User cannot be hard-
deleted while a Student row references it (see prompt: "users are never
hard-deleted; do not configure cascade from User to Student/Teacher").
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)

from ..extensions import db
from .enums import USER_ROLE_STUDENT
from .user import User


class Student(User):
    __tablename__ = "students"

    id = Column(
        Integer,
        ForeignKey("users.id"),  # no ondelete — protects User from hard-delete
        primary_key=True,
    )
    roll_number = Column(String(32), nullable=False, unique=True, index=True)
    department_id = Column(
        Integer,
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
    )
    # Current semester (1..N). Schools that don't track this can leave it
    # null at the application layer.
    semester = Column(SmallInteger, nullable=True)
    # Set to false to bar the student from registering for new exams
    # without revoking their account.
    is_eligible = Column(Boolean, nullable=False, default=True)

    # --- Relationships ----------------------------------------------------
    department = db.relationship("Department", back_populates="students")
    enrollments = db.relationship(
        "Enrollment",
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions = db.relationship(
        "ExamSession",
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __mapper_args__ = {
        "polymorphic_identity": USER_ROLE_STUDENT,
    }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Student id={self.id} roll_number={self.roll_number!r} "
            f"department_id={self.department_id}>"
        )


__all__ = ["Student"]

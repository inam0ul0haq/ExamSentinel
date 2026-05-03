"""Department entity.

A Department is a top-level organisational unit (e.g. Computer Science).
Students and teachers each belong to exactly one. Departments are seeded
during deployment (see ``docs/API.md`` §3) and never authored via the API
in v1.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, func

from ..extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    # ``name`` is the human label; case is preserved as supplied by the
    # admin who seeded the row. Uniqueness is case-sensitive at the DB
    # layer; case-insensitive lookup is handled by the service layer.
    name = Column(String(120), nullable=False, unique=True)
    # Short stable identifier used in URLs and exports (e.g. "CS").
    code = Column(String(20), nullable=False, unique=True, index=True)
    # Free-form physical/campus location string. Optional.
    campus_location = Column(String(120), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # --- Relationships ----------------------------------------------------
    # Reverse-side declarations live on ``Student`` and ``Teacher`` so
    # we can keep this module dependency-free.
    students = db.relationship(
        "Student",
        back_populates="department",
        lazy="dynamic",
    )
    teachers = db.relationship(
        "Teacher",
        back_populates="department",
        lazy="dynamic",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Department id={self.id} code={self.code!r} name={self.name!r}>"


__all__ = ["Department"]

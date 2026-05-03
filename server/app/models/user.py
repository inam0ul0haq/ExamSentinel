"""User base entity for joined-table inheritance.

Every account in the system has a ``users`` row; the role-specific data
lives in ``students`` (see :mod:`.student`) or ``teachers`` (see
:mod:`.teacher`), each of which holds a primary key that is also a
foreign key back to ``users.id``. SQLAlchemy's joined-table inheritance
keeps the join transparent at the ORM layer while preserving a clean
relational schema.

The ``role`` discriminator column is the polymorphic identity. The base
``User`` class deliberately does **not** declare a ``polymorphic_identity``
of its own, so plain ``User()`` instances cannot be persisted — every
account must be created as either a ``Student`` or a ``Teacher``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from .enums import (
    USER_ROLE_STUDENT,
    USER_ROLE_TEACHER,
    UserRoleEnum,
)


class User(db.Model):
    """Root identity entity. Use ``Student`` or ``Teacher`` to instantiate."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    # Username and email are normalised to lower-case on assignment so
    # uniqueness checks and login lookups are case-insensitive without
    # needing dialect-specific functional indexes (e.g. PG ``citext`` /
    # ``LOWER()`` indexes that wouldn't translate to SQLite in dev).
    username = Column(String(32), nullable=False, unique=True, index=True)
    email = Column(String(254), nullable=False, unique=True, index=True)

    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)

    role = Column(UserRoleEnum, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Updated by the auth service on successful login. Null until the
    # account has logged in at least once.
    last_login = Column(DateTime(timezone=True), nullable=True)

    __mapper_args__ = {
        "polymorphic_on": role,
        # No ``polymorphic_identity`` here on purpose — see module docstring.
    }

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @validates("username")
    def _normalize_username(self, _key: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip().lower()

    @validates("email")
    def _normalize_email(self, _key: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip().lower()

    # ------------------------------------------------------------------
    # Password handling (werkzeug.security)
    # ------------------------------------------------------------------
    def set_password(self, password: str) -> None:
        """Hash ``password`` with werkzeug's default scheme and store it.

        The plain-text value is never persisted; it is replaced
        immediately by the salted hash that werkzeug produces.
        """
        if not password:
            raise ValueError("password must be a non-empty string")
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password: str) -> bool:
        """Return True if ``password`` matches the stored hash."""
        if not self.password_hash or password is None:
            return False
        return check_password_hash(self.password_hash, password)

    # ------------------------------------------------------------------
    # Computed convenience properties
    # ------------------------------------------------------------------
    @property
    def is_student(self) -> bool:
        return self.role == USER_ROLE_STUDENT

    @property
    def is_teacher(self) -> bool:
        return self.role == USER_ROLE_TEACHER

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<User id={self.id} username={self.username!r} role={self.role!r}>"
        )


__all__ = ["User"]

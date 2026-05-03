"""Shared SQLAlchemy ``Enum`` column types and their string vocabularies.

Each enum is declared as plain strings (``native_enum=False``) so the
generated DDL is portable: PostgreSQL gets a ``VARCHAR + CHECK``
constraint, SQLite gets a ``TEXT + CHECK`` constraint. This avoids the
``CREATE TYPE``/``ALTER TYPE`` migration friction of native PG enums and
keeps the dev-mode SQLite fallback honest.

Module-level string constants mirror each enum's values so application
code never has to spell magic strings.
"""

from __future__ import annotations

from typing import Final, Tuple

from sqlalchemy import Enum as SAEnum


# --- Roles --------------------------------------------------------------
USER_ROLE_STUDENT: Final[str] = "student"
USER_ROLE_TEACHER: Final[str] = "teacher"
USER_ROLE_VALUES: Final[Tuple[str, ...]] = (USER_ROLE_STUDENT, USER_ROLE_TEACHER)

UserRoleEnum = SAEnum(
    *USER_ROLE_VALUES,
    name="user_role",
    native_enum=False,
    validate_strings=True,
)

# --- Enrollment status --------------------------------------------------
ENROLLMENT_STATUS_ACTIVE: Final[str] = "active"
ENROLLMENT_STATUS_DROPPED: Final[str] = "dropped"
ENROLLMENT_STATUS_VALUES: Final[Tuple[str, ...]] = (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_DROPPED,
)

EnrollmentStatusEnum = SAEnum(
    *ENROLLMENT_STATUS_VALUES,
    name="enrollment_status",
    native_enum=False,
    validate_strings=True,
)

# --- Question type ------------------------------------------------------
QUESTION_TYPE_MCQ: Final[str] = "mcq"
QUESTION_TYPE_SHORT_ANSWER: Final[str] = "short_answer"
QUESTION_TYPE_VALUES: Final[Tuple[str, ...]] = (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_SHORT_ANSWER,
)

QuestionTypeEnum = SAEnum(
    *QUESTION_TYPE_VALUES,
    name="question_type",
    native_enum=False,
    validate_strings=True,
)

# --- MCQ correct option letter -----------------------------------------
CORRECT_OPTION_A: Final[str] = "A"
CORRECT_OPTION_B: Final[str] = "B"
CORRECT_OPTION_C: Final[str] = "C"
CORRECT_OPTION_D: Final[str] = "D"
CORRECT_OPTION_VALUES: Final[Tuple[str, ...]] = (
    CORRECT_OPTION_A,
    CORRECT_OPTION_B,
    CORRECT_OPTION_C,
    CORRECT_OPTION_D,
)

CorrectOptionEnum = SAEnum(
    *CORRECT_OPTION_VALUES,
    name="correct_option",
    native_enum=False,
    validate_strings=True,
)

# --- ExamSession lifecycle ---------------------------------------------
SESSION_STATUS_PRE_CHECK: Final[str] = "pre_check"
SESSION_STATUS_IN_PROGRESS: Final[str] = "in_progress"
SESSION_STATUS_SUBMITTED: Final[str] = "submitted"
SESSION_STATUS_EXPIRED: Final[str] = "expired"
SESSION_STATUS_ABORTED_VM: Final[str] = "aborted_vm"
SESSION_STATUS_ABORTED_STEALTH_VM: Final[str] = "aborted_stealth_vm"
SESSION_STATUS_VALUES: Final[Tuple[str, ...]] = (
    SESSION_STATUS_PRE_CHECK,
    SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_SUBMITTED,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_ABORTED_VM,
    SESSION_STATUS_ABORTED_STEALTH_VM,
)

SessionStatusEnum = SAEnum(
    *SESSION_STATUS_VALUES,
    name="session_status",
    native_enum=False,
    validate_strings=True,
)

# --- Incident severity --------------------------------------------------
INCIDENT_SEVERITY_INFO: Final[str] = "info"
INCIDENT_SEVERITY_WARNING: Final[str] = "warning"
INCIDENT_SEVERITY_CRITICAL: Final[str] = "critical"
INCIDENT_SEVERITY_VALUES: Final[Tuple[str, ...]] = (
    INCIDENT_SEVERITY_INFO,
    INCIDENT_SEVERITY_WARNING,
    INCIDENT_SEVERITY_CRITICAL,
)

IncidentSeverityEnum = SAEnum(
    *INCIDENT_SEVERITY_VALUES,
    name="incident_severity",
    native_enum=False,
    validate_strings=True,
)


__all__ = [
    "USER_ROLE_STUDENT",
    "USER_ROLE_TEACHER",
    "USER_ROLE_VALUES",
    "UserRoleEnum",
    "ENROLLMENT_STATUS_ACTIVE",
    "ENROLLMENT_STATUS_DROPPED",
    "ENROLLMENT_STATUS_VALUES",
    "EnrollmentStatusEnum",
    "QUESTION_TYPE_MCQ",
    "QUESTION_TYPE_SHORT_ANSWER",
    "QUESTION_TYPE_VALUES",
    "QuestionTypeEnum",
    "CORRECT_OPTION_A",
    "CORRECT_OPTION_B",
    "CORRECT_OPTION_C",
    "CORRECT_OPTION_D",
    "CORRECT_OPTION_VALUES",
    "CorrectOptionEnum",
    "SESSION_STATUS_PRE_CHECK",
    "SESSION_STATUS_IN_PROGRESS",
    "SESSION_STATUS_SUBMITTED",
    "SESSION_STATUS_EXPIRED",
    "SESSION_STATUS_ABORTED_VM",
    "SESSION_STATUS_ABORTED_STEALTH_VM",
    "SESSION_STATUS_VALUES",
    "SessionStatusEnum",
    "INCIDENT_SEVERITY_INFO",
    "INCIDENT_SEVERITY_WARNING",
    "INCIDENT_SEVERITY_CRITICAL",
    "INCIDENT_SEVERITY_VALUES",
    "IncidentSeverityEnum",
]

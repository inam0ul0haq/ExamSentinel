"""SQLAlchemy model registry.

Importing this package side-loads every model module so that
``db.metadata`` is fully populated before Alembic runs autogenerate or
the test suite calls ``db.create_all()``. Application code should
prefer importing the specific class it needs:

    from app.models import User, Course

…but ``from app.models import *`` is also supported (per the Definition
of Done for Part 6).
"""

from __future__ import annotations

from .answer import Answer
from .course import Course
from .department import Department
from .enrollment import Enrollment
from .exam import Exam
from .exam_session import ExamSession
from .incident_log import IncidentLog
from .question import Question
from .student import Student
from .teacher import Teacher
from .user import User


__all__ = [
    "Answer",
    "Course",
    "Department",
    "Enrollment",
    "Exam",
    "ExamSession",
    "IncidentLog",
    "Question",
    "Student",
    "Teacher",
    "User",
]

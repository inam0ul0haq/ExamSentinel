"""Question entity.

Questions belong to exactly one Exam and are ordered by ``order_index``.
The schema follows the user prompt's explicit shape: four discrete
option columns (``option_a``..``option_d``) plus a ``correct_option``
letter enum, rather than a JSON ``options`` array. For
``short_answer`` questions every MCQ-only column must be NULL.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
)

from ..extensions import db
from .enums import (
    CorrectOptionEnum,
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_SHORT_ANSWER,
    QuestionTypeEnum,
)


class Question(db.Model):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    exam_id = Column(
        Integer,
        ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Free-form prompt text (capped at 4000 chars per API contract).
    prompt = Column(String(4000), nullable=False)
    question_type = Column(QuestionTypeEnum, nullable=False)
    marks = Column(Integer, nullable=False)

    # MCQ-only columns. All four are nullable so ``short_answer`` rows
    # can leave them empty.
    option_a = Column(String(500), nullable=True)
    option_b = Column(String(500), nullable=True)
    option_c = Column(String(500), nullable=True)
    option_d = Column(String(500), nullable=True)
    correct_option = Column(CorrectOptionEnum, nullable=True)

    # 1-indexed display order within the exam. The service layer enforces
    # uniqueness within an exam at insert/update time; we leave it as a
    # plain int here so re-ordering doesn't violate a DB constraint mid-
    # transaction.
    order_index = Column(Integer, nullable=False)

    __table_args__ = (
        # Sanity: ``marks`` must be positive.
        CheckConstraint("marks > 0", name="ck_questions_marks_positive"),
    )

    # --- Relationships ----------------------------------------------------
    exam = db.relationship("Exam", back_populates="questions")
    answers = db.relationship(
        "Answer",
        back_populates="question",
        passive_deletes=True,
        # No cascade here — answers are owned by the session and are
        # cleaned up via ``ExamSession.answers`` cascade.
    )

    # --- Convenience ------------------------------------------------------
    @property
    def is_mcq(self) -> bool:
        return self.question_type == QUESTION_TYPE_MCQ

    @property
    def is_short_answer(self) -> bool:
        return self.question_type == QUESTION_TYPE_SHORT_ANSWER

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Question id={self.id} exam_id={self.exam_id} "
            f"type={self.question_type!r} order={self.order_index}>"
        )


__all__ = ["Question"]

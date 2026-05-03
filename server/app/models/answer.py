"""Answer entity — one student response per question per session.

Auto-save semantics: the latest write wins, and the upsert is keyed on
the composite ``(session_id, question_id)`` uniqueness constraint.
``marks_awarded`` is null until grading runs (auto for MCQs, manual for
short-answer); ``is_auto_graded`` flips to true once the auto-grader has
processed the row.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from ..extensions import db


class Answer(db.Model):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer,
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey("questions.id"),  # no cascade — answers cleaned via session
        nullable=False,
        index=True,
    )

    # For MCQs this stores the chosen option letter (``A`` / ``B`` /
    # ``C`` / ``D``); for short-answer questions it stores free-form
    # prose up to 8000 chars (per API contract).
    answer_text = Column(String(8000), nullable=True)
    marks_awarded = Column(Float, nullable=True)
    is_auto_graded = Column(Boolean, nullable=False, default=False)

    # Updated to ``func.now()`` on every upsert so the client can render
    # "Saved at HH:MM" indicators.
    saved_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "question_id",
            name="uq_answers_session_question",
        ),
    )

    # --- Relationships ----------------------------------------------------
    session = db.relationship("ExamSession", back_populates="answers")
    question = db.relationship("Question", back_populates="answers")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Answer id={self.id} session_id={self.session_id} "
            f"question_id={self.question_id} marks_awarded={self.marks_awarded}>"
        )


__all__ = ["Answer"]

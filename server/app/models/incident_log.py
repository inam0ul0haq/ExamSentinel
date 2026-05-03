"""IncidentLog entity — append-only forensic record per session.

Incidents are emitted by the desktop client during pre-check, in-
progress, and post phases of a session. The full controlled vocabulary
for ``incident_type`` lives in :mod:`app.utils.incident_types`; the
column itself is a plain string so adding new types in the future is a
code-only change rather than a schema migration.

The three optional forensic columns (``cpu_thermal_value``,
``timing_latency_ms``, ``evidence_path``) are populated only for
incident kinds that produce that signal (e.g. stealth-VM thermal/timing
samples, blacklisted-process kills with a screenshot path).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)

from ..extensions import db
from .enums import IncidentSeverityEnum


class IncidentLog(db.Model):
    __tablename__ = "incident_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer,
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Server-side receive timestamp. Defaults to ``now()`` so simple
    # inserts don't have to populate it; the service layer overrides
    # this when ingesting client-supplied ``client_timestamp`` values.
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Plain string with a controlled vocabulary (see
    # ``app.utils.incident_types``). Validation lives at the service
    # layer; the model intentionally does not constrain values so adding
    # a new type is migration-free.
    incident_type = Column(String(64), nullable=False, index=True)
    severity = Column(IncidentSeverityEnum, nullable=False, index=True)

    description = Column(String(2000), nullable=True)

    # --- Optional forensic columns ---------------------------------------
    cpu_thermal_value = Column(Float, nullable=True)
    timing_latency_ms = Column(Float, nullable=True)
    evidence_path = Column(String(500), nullable=True)

    __table_args__ = (
        Index(
            "ix_incident_logs_session_occurred",
            "session_id",
            "occurred_at",
        ),
    )

    # --- Relationships ----------------------------------------------------
    session = db.relationship("ExamSession", back_populates="incidents")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<IncidentLog id={self.id} session_id={self.session_id} "
            f"type={self.incident_type!r} severity={self.severity!r}>"
        )


__all__ = ["IncidentLog"]

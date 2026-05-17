"""Service layer for incident ingestion.

Validates and persists IncidentLog rows on behalf of the incidents
blueprint. The blueprint never touches the ORM directly; this module
owns all incident-related business logic so the same rules apply
whether the entry point is the single-incident POST, the bulk POST,
or a future internal caller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..extensions import db
from ..models import IncidentLog
from ..models.enums import (
    INCIDENT_SEVERITY_VALUES,
    SESSION_STATUS_SUBMITTED,
)
from ..models.exam_session import ExamSession
from ..utils.incident_types import is_valid_incident_type
from ..utils.responses import error_response, validation_error


# Sessions that have been fully finalised cannot accept more incidents.
# Per the prompt, allowed non-final states are pre_check, in_progress,
# expired plus the two aborted_* states (which are terminal but should
# still accept any in-flight forensic events the client queued before
# the abort transition committed).
_FINAL_STATUSES_REJECTING_INCIDENTS = frozenset({SESSION_STATUS_SUBMITTED})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate_incident_payload(
    payload: Any,
    index: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[Tuple]]:
    """Return ``(cleaned, error_tuple_or_None)``.

    ``index`` is used to prefix field paths for bulk requests so the
    client knows which list element failed (e.g. ``incidents.3.type``).
    """
    prefix = "" if index is None else f"incidents.{index}."

    if not isinstance(payload, dict):
        return {}, validation_error(
            {f"{prefix}_": ["Incident must be a JSON object."]}
        )

    field_errors: Dict[str, List[str]] = {}

    # type ---------------------------------------------------------------
    incident_type = payload.get("type")
    if not isinstance(incident_type, str) or not incident_type.strip():
        field_errors[f"{prefix}type"] = ["Type is required."]
    elif not is_valid_incident_type(incident_type.strip()):
        field_errors[f"{prefix}type"] = [
            "Type is not in the controlled vocabulary."
        ]

    # severity -----------------------------------------------------------
    severity = payload.get("severity")
    if not isinstance(severity, str) or not severity.strip():
        field_errors[f"{prefix}severity"] = ["Severity is required."]
    elif severity not in INCIDENT_SEVERITY_VALUES:
        field_errors[f"{prefix}severity"] = [
            "Severity must be one of: " + ", ".join(INCIDENT_SEVERITY_VALUES)
        ]

    # description --------------------------------------------------------
    description = payload.get("description")
    if description is not None:
        if not isinstance(description, str):
            field_errors[f"{prefix}description"] = [
                "Description must be a string when provided."
            ]
        elif len(description) > 2000:
            field_errors[f"{prefix}description"] = [
                "Description must be at most 2000 characters."
            ]

    # Optional forensic numeric fields ----------------------------------
    cpu_thermal_value = payload.get("cpu_thermal_value")
    if cpu_thermal_value is not None:
        try:
            cpu_thermal_value = float(cpu_thermal_value)
        except (TypeError, ValueError):
            field_errors[f"{prefix}cpu_thermal_value"] = [
                "cpu_thermal_value must be a number when provided."
            ]
            cpu_thermal_value = None

    timing_latency_ms = payload.get("timing_latency_ms")
    if timing_latency_ms is not None:
        try:
            timing_latency_ms = float(timing_latency_ms)
        except (TypeError, ValueError):
            field_errors[f"{prefix}timing_latency_ms"] = [
                "timing_latency_ms must be a number when provided."
            ]
            timing_latency_ms = None

    evidence_path = payload.get("evidence_path")
    if evidence_path is not None:
        if not isinstance(evidence_path, str):
            field_errors[f"{prefix}evidence_path"] = [
                "evidence_path must be a string when provided."
            ]
            evidence_path = None
        elif len(evidence_path) > 500:
            field_errors[f"{prefix}evidence_path"] = [
                "evidence_path must be at most 500 characters."
            ]

    if field_errors:
        return {}, validation_error(field_errors)

    return {
        "incident_type": incident_type.strip(),
        "severity": severity,
        "description": (description.strip() if isinstance(description, str)
                        else None),
        "cpu_thermal_value": cpu_thermal_value,
        "timing_latency_ms": timing_latency_ms,
        "evidence_path": evidence_path,
    }, None


def can_ingest_incidents_for(session: ExamSession) -> Optional[Tuple]:
    """Return an ``error_response`` tuple if the session cannot accept
    new incidents, else ``None``.
    """
    if session.status in _FINAL_STATUSES_REJECTING_INCIDENTS:
        return error_response(
            "conflict",
            "Session is finalised and cannot accept new incidents.",
            409,
            details={"code": "session_finalised"},
        )
    return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _serialize_incident(incident: IncidentLog) -> Dict[str, Any]:
    return {
        "id": incident.id,
        "session_id": incident.session_id,
        "type": incident.incident_type,
        "severity": incident.severity,
        "description": incident.description,
        "cpu_thermal_value": incident.cpu_thermal_value,
        "timing_latency_ms": incident.timing_latency_ms,
        "evidence_path": incident.evidence_path,
        "occurred_at": (
            incident.occurred_at.isoformat()
            if incident.occurred_at
            else None
        ),
    }


def create_incident(
    session: ExamSession,
    payload: Mapping[str, Any],
) -> Tuple[Dict[str, Any], Optional[Tuple]]:
    """Persist a single incident. Returns ``(serialized, error_or_None)``.

    ``occurred_at`` is always set to the server's current UTC time;
    client-supplied timestamps are ignored to prevent backdating.
    """
    state_error = can_ingest_incidents_for(session)
    if state_error is not None:
        return {}, state_error

    cleaned, err = _validate_incident_payload(payload)
    if err is not None:
        return {}, err

    incident = IncidentLog(
        session_id=session.id,
        occurred_at=datetime.now(timezone.utc),
        incident_type=cleaned["incident_type"],
        severity=cleaned["severity"],
        description=cleaned["description"],
        cpu_thermal_value=cleaned["cpu_thermal_value"],
        timing_latency_ms=cleaned["timing_latency_ms"],
        evidence_path=cleaned["evidence_path"],
    )
    db.session.add(incident)
    db.session.commit()
    db.session.refresh(incident)
    return _serialize_incident(incident), None


def create_incidents_bulk(
    session: ExamSession,
    items: Any,
) -> Tuple[List[Dict[str, Any]], Optional[Tuple]]:
    """Persist a list of incidents in a single transaction."""
    state_error = can_ingest_incidents_for(session)
    if state_error is not None:
        return [], state_error

    if not isinstance(items, list) or not items:
        return [], validation_error(
            {"incidents": ["Field must be a non-empty list of incidents."]}
        )

    if len(items) > 500:
        return [], validation_error(
            {"incidents": ["At most 500 incidents may be posted in one call."]}
        )

    cleaned_rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        cleaned, err = _validate_incident_payload(item, index=idx)
        if err is not None:
            return [], err
        cleaned_rows.append(cleaned)

    now = datetime.now(timezone.utc)
    created: List[IncidentLog] = []
    for row in cleaned_rows:
        incident = IncidentLog(
            session_id=session.id,
            occurred_at=now,
            incident_type=row["incident_type"],
            severity=row["severity"],
            description=row["description"],
            cpu_thermal_value=row["cpu_thermal_value"],
            timing_latency_ms=row["timing_latency_ms"],
            evidence_path=row["evidence_path"],
        )
        db.session.add(incident)
        created.append(incident)

    db.session.commit()
    for inc in created:
        db.session.refresh(inc)

    return [_serialize_incident(inc) for inc in created], None


__all__ = [
    "create_incident",
    "create_incidents_bulk",
    "can_ingest_incidents_for",
]

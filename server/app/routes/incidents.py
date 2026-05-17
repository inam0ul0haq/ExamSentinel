"""Incident ingestion blueprint.

Two endpoints, both student-only and both scoped to a session the
caller owns:

* ``POST /sessions/<session_id>/incident``  — single incident
* ``POST /sessions/<session_id>/incidents`` — bulk list (used by the
  desktop client's offline-queue flusher when reconnecting)

Both return ``201`` with the persisted row(s). ``occurred_at`` is
always the server's clock; any client-supplied timestamp is ignored to
prevent backdating.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models.exam_session import ExamSession
from ..services.incident_service import (
    create_incident,
    create_incidents_bulk,
)
from ..utils.auth_decorators import current_user, student_required
from ..utils.responses import error_response


incidents_bp = Blueprint("incidents", __name__)


def _load_owned_session(session_id: int):
    """Return ``(session, error_tuple_or_None)``.

    Enforces that the JWT belongs to the student that owns the session.
    Order matters: 404 wins over 403 for sessions that simply do not
    exist (avoids leaking the existence of other students' sessions).
    """
    session = db.session.get(ExamSession, session_id)
    if session is None:
        return None, error_response("not_found", "Session not found.", 404)

    user = current_user()
    if session.student_id != user.id:
        return None, error_response(
            "forbidden",
            "You do not own this session.",
            403,
        )
    return session, None


@incidents_bp.post("/sessions/<int:session_id>/incident")
@student_required
def post_incident(session_id: int):
    session, err = _load_owned_session(session_id)
    if err is not None:
        return err

    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(
            "bad_request",
            "Request body must be a JSON object.",
            400,
        )

    body, err = create_incident(session, payload)
    if err is not None:
        return err
    return jsonify(body), 201


@incidents_bp.post("/sessions/<int:session_id>/incidents")
@student_required
def post_incidents_bulk(session_id: int):
    session, err = _load_owned_session(session_id)
    if err is not None:
        return err

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            "bad_request",
            "Request body must be a JSON object with an ``incidents`` list.",
            400,
        )

    items, err = create_incidents_bulk(session, payload.get("incidents"))
    if err is not None:
        return err
    return jsonify({"items": items, "count": len(items)}), 201


__all__ = ["incidents_bp"]

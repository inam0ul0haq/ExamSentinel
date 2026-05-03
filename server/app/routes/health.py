"""Health check blueprint.

Exposes ``GET /api/v1/health`` (the ``/api/v1`` prefix is applied at
blueprint registration time inside the application factory). The response
intentionally avoids leaking the database connection string; only the
SQLAlchemy dialect name is reported.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify
from sqlalchemy.engine.url import make_url


health_bp = Blueprint("health", __name__)


def _resolved_db_dialect() -> str:
    """Return the SQLAlchemy dialect name (e.g. ``sqlite``, ``postgresql``).

    Parsed from ``SQLALCHEMY_DATABASE_URI`` so we never echo credentials or
    host information back to the caller.
    """
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri:
        return "unknown"
    try:
        return make_url(uri).get_backend_name()
    except Exception:  # pragma: no cover - defensive, should never trip
        return "unknown"


@health_bp.get("/health")
def health() -> tuple:
    """Lightweight liveness probe used by Railway and the desktop client."""
    payload = {
        "status": "ok",
        "api_version": current_app.config.get("API_VERSION", "v1"),
        "database": _resolved_db_dialect(),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return jsonify(payload), 200

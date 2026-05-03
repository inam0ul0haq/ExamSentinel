"""Health check blueprint.

Exposes ``GET /api/v1/health`` (the ``/api/v1`` prefix is applied at
blueprint registration time inside the application factory). The response
intentionally avoids leaking the database connection string; only the
SQLAlchemy dialect name is reported.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from ..extensions import db


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
    """Lightweight liveness probe used by Railway and the desktop client.

    Runs a trivial ``SELECT 1`` against the configured database so the
    response reflects real connectivity (and so the SQLite fallback file
    is materialised on first hit in development).
    """
    dialect = _resolved_db_dialect()
    status = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - surface real failures
        current_app.logger.warning("health check db probe failed: %s", exc)
        status = "degraded"

    payload = {
        "status": status,
        "version": current_app.config.get("API_VERSION", "v1"),
        "database": dialect,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    http_status = 200 if status == "ok" else 503
    return jsonify(payload), http_status

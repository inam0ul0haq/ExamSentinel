"""Flask extension singletons.

These objects are created once at import time and bound to the Flask app
inside the application factory. Keeping them in a dedicated module avoids
circular imports between ``app/__init__.py`` and modules that need ``db``
(models, services) once those land in later parts of the project.
"""

from __future__ import annotations

import sqlite3

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine


# Single SQLAlchemy instance shared across the app. Models attach to
# ``db.Model`` from their own modules under ``app/models/``.
db = SQLAlchemy()

# Alembic-backed migration manager. ``migrations/`` lives at server/migrations.
migrate = Migrate()

# CORS is configured per-app inside the factory so origins can be derived
# from the runtime config rather than baked in here.
cors = CORS()

# Flask-JWT-Extended manager. The identity callback, additional-claims
# callback, and error handlers are bound to this instance inside the
# application factory (see ``app/__init__.py``). Tokens are HS256-signed
# with ``JWT_SECRET_KEY`` and expire twelve hours after issuance per
# ``docs/API.md`` §1.3.
jwt = JWTManager()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enable foreign-key enforcement for SQLite connections.

    SQLite ships with FK constraints **disabled** by default — every
    new connection has to issue ``PRAGMA foreign_keys = ON`` before
    ``ON DELETE CASCADE`` clauses do anything. Without this hook the
    SQLite dev fallback would silently leave orphaned rows after a
    parent delete, masking real cascade bugs that PostgreSQL would
    catch in production.

    The hook is a no-op for non-SQLite connections.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

"""Application factory for the ExamSentinel Flask backend.

The factory pattern lets us produce isolated app instances for tests,
WSGI workers, and the dev runner without relying on global state. Models,
auth, and feature blueprints are intentionally absent at this stage —
this skeleton wires only configuration, extensions, and the health check.
"""

from __future__ import annotations

import os
from typing import Type

from flask import Flask, jsonify

from .config import Config, ConfigError
from .extensions import cors, db, migrate
from .routes.health import health_bp


# Absolute path to ``server/migrations``. Resolving it from the package
# location (rather than from cwd) lets ``flask --app server.wsgi db ...``
# find the alembic scripts whether the caller runs from the repo root
# (Railway release phase) or from ``server/`` (local development).
_MIGRATIONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "migrations")
)


def create_app(config_class: Type[Config] = Config) -> Flask:
    """Build and return a configured Flask application instance."""

    # Validate environment up-front so misconfiguration is fatal at boot,
    # not on the first request to a protected route.
    config_class.validate()

    app = Flask(__name__)
    app.config.from_object(config_class)

    _init_extensions(app, config_class)
    _register_blueprints(app, config_class)
    _register_error_handlers(app)

    return app


def _init_extensions(app: Flask, config_class: Type[Config]) -> None:
    """Bind SQLAlchemy, Migrate, and CORS to the app."""

    # Side-effect import: registers every model class with ``db.metadata``
    # so Flask-Migrate autogenerate and ``db.create_all()`` see the full
    # schema. Done before ``init_app`` for clarity; order is irrelevant
    # because models only reference ``db`` at class-definition time.
    from . import models  # noqa: F401

    db.init_app(app)
    # Bind alembic to the absolute ``server/migrations`` path so the
    # Railway release phase (``flask --app server.wsgi db upgrade``)
    # finds the scripts when invoked from the repository root, and
    # local invocations from ``server/`` keep working unchanged.
    migrate.init_app(app, db, directory=_MIGRATIONS_DIR)

    origins = config_class.CORS_ALLOWED_ORIGINS
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=origins != "*",
    )


def _register_blueprints(app: Flask, config_class: Type[Config]) -> None:
    """Mount feature blueprints under the versioned API prefix."""

    prefix = config_class.API_PREFIX  # ``/api/v1``
    app.register_blueprint(health_bp, url_prefix=prefix)


def _register_error_handlers(app: Flask) -> None:
    """Install the API error envelope (see docs/API.md §1.5).

    Only the catch-all 404/405/500 handlers are registered at this stage.
    Per-endpoint validation errors land in later parts.
    """

    def _envelope(code: str, message: str, status: int):
        return (
            jsonify({"error": {"code": code, "message": message}}),
            status,
        )

    @app.errorhandler(404)
    def _not_found(_err):
        return _envelope("not_found", "Resource not found.", 404)

    @app.errorhandler(405)
    def _method_not_allowed(_err):
        return _envelope("method_not_allowed", "Method not allowed.", 405)

    @app.errorhandler(500)
    def _internal_error(_err):
        return _envelope("internal_error", "Internal server error.", 500)


__all__ = ["create_app", "Config", "ConfigError"]

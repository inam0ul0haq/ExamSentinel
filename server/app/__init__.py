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
from .extensions import cors, db, jwt, migrate
from .routes.auth import auth_bp
from .routes.courses import courses_bp
from .routes.departments import departments_bp, users_bp
from .routes.diag import diag_bp
from .routes.exams import exams_bp
from .routes.health import health_bp
from .routes.sessions import sessions_bp
from .utils.responses import make_error_response


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
    """Bind SQLAlchemy, Migrate, CORS, and JWT to the app."""

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

    jwt.init_app(app)
    _register_jwt_callbacks()


def _register_blueprints(app: Flask, config_class: Type[Config]) -> None:
    """Mount feature blueprints under the versioned API prefix."""

    prefix = config_class.API_PREFIX  # ``/api/v1``
    app.register_blueprint(health_bp, url_prefix=prefix)
    app.register_blueprint(auth_bp, url_prefix=f"{prefix}/auth")
    # TODO(part_12_remove_diag_routes): drop this blueprint registration
    # together with ``app/routes/diag.py`` once the role decorators have
    # been verified by Part 8 of the build plan.
    app.register_blueprint(diag_bp, url_prefix=f"{prefix}/_diag")
    # Departments and users endpoints
    app.register_blueprint(departments_bp, url_prefix=f"{prefix}/departments")
    app.register_blueprint(users_bp, url_prefix=f"{prefix}/users")
    # Courses and enrollments endpoints
    app.register_blueprint(courses_bp, url_prefix=f"{prefix}/courses")
    # Exams and sessions endpoints
    app.register_blueprint(exams_bp, url_prefix=prefix)
    app.register_blueprint(sessions_bp, url_prefix=prefix)


def _register_jwt_callbacks() -> None:
    """Bind identity, additional-claims, and error callbacks to the JWT manager.

    Identity claim is the User row's primary key serialised as a string
    (per the JWT spec for the ``sub`` claim). The additional-claims
    callback injects the user's role so authorisation decorators can
    reject mismatches without a second database round-trip.
    """
    from .models import User  # local import: app/__init__ imports this module

    @jwt.user_identity_loader
    def _identity_lookup(user):
        # ``user`` is whatever was passed to ``create_access_token``.
        # The auth blueprint always passes a ``User`` instance; defensive
        # branches accept a bare id for completeness (e.g. test helpers).
        if isinstance(user, User):
            return str(user.id)
        return str(user)

    @jwt.additional_claims_loader
    def _additional_claims(user):
        # Mirror the identity-loader contract: prefer the role on the
        # ``User`` instance; fall back to a lookup if a bare id was
        # passed. A missing user yields an empty claim block — the
        # decorators will then 403 on role mismatch rather than crashing.
        if isinstance(user, User):
            return {"role": user.role}
        try:
            user_id = int(user)
        except (TypeError, ValueError):
            return {}
        loaded = db.session.get(User, user_id)
        return {"role": loaded.role} if loaded else {}

    @jwt.expired_token_loader
    def _expired_token(_jwt_header, _jwt_payload):
        return make_error_response(
            "token_expired",
            "Authentication token has expired.",
            401,
        )

    @jwt.invalid_token_loader
    def _invalid_token(_reason):
        return make_error_response(
            "unauthorized",
            "Authentication token is invalid.",
            401,
        )

    @jwt.unauthorized_loader
    def _missing_token(_reason):
        return make_error_response(
            "unauthorized",
            "Authentication token is required.",
            401,
        )

    @jwt.needs_fresh_token_loader
    def _needs_fresh_token(_jwt_header, _jwt_payload):
        # We don't issue fresh-vs-non-fresh tokens, but Flask-JWT-Extended
        # requires the callback to exist for completeness. Treat any
        # request that hits this branch as plain 401.
        return make_error_response(
            "unauthorized",
            "A fresh authentication token is required.",
            401,
        )

    @jwt.revoked_token_loader
    def _revoked_token(_jwt_header, _jwt_payload):
        # Revocation is not implemented in v1; the callback is wired so
        # any future revocation logic returns the standard envelope.
        return make_error_response(
            "unauthorized",
            "Authentication token has been revoked.",
            401,
        )


def _register_error_handlers(app: Flask) -> None:
    """Install the API error envelope (see docs/API.md §1.5).

    Only the catch-all 4xx/5xx handlers are registered here. Route-level
    validation errors are produced by helpers in ``app/utils/responses.py``.
    """

    def _envelope(code: str, message: str, status: int):
        return (
            jsonify({"error": {"code": code, "message": message}}),
            status,
        )

    @app.errorhandler(400)
    def _bad_request(_err):
        return _envelope("bad_request", "Malformed request.", 400)

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

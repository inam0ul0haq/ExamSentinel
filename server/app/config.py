"""Environment-driven configuration for the ExamSentinel Flask backend.

Configuration is loaded exclusively from environment variables. No secret
or credential is ever hardcoded here. The Config class is consumed by the
application factory via ``app.config.from_object(Config)``.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import List


# Repository-relative path used as the SQLite fallback in development so the
# server runs without a Postgres install. Resolved to an absolute path so
# SQLAlchemy is happy regardless of the process cwd.
_SERVER_ROOT = Path(__file__).resolve().parent.parent
_DEV_SQLITE_PATH = _SERVER_ROOT / "dev.db"


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


def _split_origins(raw: str) -> List[str]:
    """Parse a comma-separated CORS origin list, trimming and dropping blanks."""
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def _resolve_database_uri(database_url: str | None, flask_env: str) -> str:
    """Resolve the SQLAlchemy database URI from DATABASE_URL.

    Falls back to a local SQLite file ONLY when ``FLASK_ENV`` is ``development``.
    In any other environment a missing ``DATABASE_URL`` is a hard startup error
    so we never silently boot production against an ephemeral SQLite file.
    """
    if database_url:
        # Railway/Heroku style ``postgres://`` URLs are rejected by SQLAlchemy
        # 1.4+; normalise them to the explicit ``postgresql://`` form.
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        return database_url

    if flask_env == "development":
        return f"sqlite:///{_DEV_SQLITE_PATH.as_posix()}"

    raise ConfigError(
        "DATABASE_URL is required when FLASK_ENV is not 'development'. "
        "Set DATABASE_URL to a valid PostgreSQL connection string."
    )


class Config:
    """Application configuration sourced from environment variables.

    All attributes are resolved at class-definition time. Tests that need a
    different configuration should construct a subclass or override values on
    the Flask ``app.config`` mapping after the factory has run.
    """

    # --- Environment ------------------------------------------------------
    FLASK_ENV: str = os.environ.get("FLASK_ENV", "development").strip().lower()
    DEBUG: bool = FLASK_ENV == "development"
    TESTING: bool = False

    # --- Networking -------------------------------------------------------
    # PORT is consumed by the dev runner / gunicorn launcher, not by Flask
    # itself, but we surface it on the config object so callers have one
    # source of truth.
    PORT: int = int(os.environ.get("PORT", "5000"))

    # --- Secrets ----------------------------------------------------------
    SECRET_KEY: str | None = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY: str | None = os.environ.get("JWT_SECRET_KEY")

    # --- JWT --------------------------------------------------------------
    # Twelve-hour access-token lifetime per docs/API.md §1.3. The value is
    # surfaced as both a ``timedelta`` (consumed by Flask-JWT-Extended) and
    # an integer seconds constant (echoed back to clients in the
    # ``expires_in`` field of /auth/login).
    JWT_ACCESS_TOKEN_SECONDS: int = 12 * 60 * 60  # 43200
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(seconds=JWT_ACCESS_TOKEN_SECONDS)
    # The auth blueprint relies on the standard Authorization: Bearer
    # header transport; cookies and query-string tokens are intentionally
    # disabled.
    JWT_TOKEN_LOCATION: List[str] = ["headers"]
    JWT_HEADER_NAME: str = "Authorization"
    JWT_HEADER_TYPE: str = "Bearer"

    # --- Database ---------------------------------------------------------
    SQLALCHEMY_DATABASE_URI: str = _resolve_database_uri(
        os.environ.get("DATABASE_URL"), FLASK_ENV
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    # Recycle connections to dodge Railway/Postgres idle-timeout drops.
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- CORS -------------------------------------------------------------
    # ``CORS_ALLOWED_ORIGINS`` is a comma-separated list. The wildcard ``*``
    # default is only permitted in development; non-dev environments must
    # opt-in to specific origins via the env var.
    _raw_cors: str = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if _raw_cors:
        if _raw_cors == "*":
            CORS_ALLOWED_ORIGINS: List[str] | str = "*"
        else:
            CORS_ALLOWED_ORIGINS = _split_origins(_raw_cors)
    else:
        CORS_ALLOWED_ORIGINS = "*" if FLASK_ENV == "development" else []

    # --- API metadata -----------------------------------------------------
    API_VERSION: str = "v1"
    API_PREFIX: str = "/api/v1"

    @classmethod
    def validate(cls) -> None:
        """Raise ``ConfigError`` if any required value is missing.

        Called by the factory before the app is returned so misconfiguration
        is loud and immediate rather than surfacing as a 500 on first request.
        """
        problems: list[str] = []

        if not cls.SECRET_KEY:
            if cls.FLASK_ENV == "development":
                cls.SECRET_KEY = "dev-insecure-secret-key-change-me"
            else:
                problems.append("SECRET_KEY is required outside development.")

        if not cls.JWT_SECRET_KEY:
            if cls.FLASK_ENV == "development":
                cls.JWT_SECRET_KEY = "dev-insecure-jwt-secret-change-me"
            else:
                problems.append("JWT_SECRET_KEY is required outside development.")

        if cls.FLASK_ENV != "development" and cls.CORS_ALLOWED_ORIGINS == "*":
            problems.append(
                "CORS_ALLOWED_ORIGINS='*' is forbidden outside development; "
                "set an explicit comma-separated origin list."
            )

        if problems:
            raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(problems))

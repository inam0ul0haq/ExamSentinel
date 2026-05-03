"""WSGI entry point used by gunicorn (Railway production runtime).

Railway's start command is ``gunicorn wsgi:app`` (see ``Procfile``). Importing
this module triggers the application factory once at worker boot.
"""

from __future__ import annotations

from dotenv import load_dotenv

# Load .env if present. In production (Railway) the env is already populated
# by the platform; ``load_dotenv`` is a no-op when the file is absent.
load_dotenv()

from app import create_app  # noqa: E402  (import after dotenv on purpose)


app = create_app()

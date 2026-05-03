"""WSGI entry point used by gunicorn (Railway production runtime).

Two callers import this module from two different working directories:

1. ``gunicorn --chdir server wsgi:app`` — invoked by the Procfile ``web``
   process; cwd is ``server/``, the import path is ``wsgi``.
2. ``flask --app server.wsgi db upgrade`` — invoked by the Procfile
   ``release`` phase; cwd is the repository root, the import path is
   ``server.wsgi`` (resolved via PEP 420 namespace packages because
   ``server/`` has no ``__init__.py``).

In case (2), Python's import machinery does **not** add ``server/`` to
``sys.path``, so the bare ``from app import create_app`` line below
would fail. We fix that by self-locating the directory containing this
file and prepending it to ``sys.path``. The insert is a no-op in case
(1) because ``server/`` is already first on ``sys.path`` (gunicorn adds
its cwd).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


# Make ``server/`` importable regardless of the caller's cwd. ``app``
# (the package at ``server/app/``) must resolve to a top-level import.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Load .env if present. In production (Railway) the env is already
# populated by the platform; ``load_dotenv`` is a no-op when the file
# is absent.
load_dotenv()

from app import create_app  # noqa: E402  (import after dotenv on purpose)


app = create_app()

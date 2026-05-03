"""Flask extension singletons.

These objects are created once at import time and bound to the Flask app
inside the application factory. Keeping them in a dedicated module avoids
circular imports between ``app/__init__.py`` and modules that need ``db``
(models, services) once those land in later parts of the project.
"""

from __future__ import annotations

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


# Single SQLAlchemy instance shared across the app. Models will attach to
# ``db.Model`` in Part 6; this skeleton creates the instance only.
db = SQLAlchemy()

# Alembic-backed migration manager. ``migrations/`` lives at server/migrations.
migrate = Migrate()

# CORS is configured per-app inside the factory so origins can be derived
# from the runtime config rather than baked in here.
cors = CORS()

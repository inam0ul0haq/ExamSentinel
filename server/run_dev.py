"""Local development server entry point.

Usage (from the ``server/`` directory):

    python run_dev.py

The dev server reads ``PORT`` from the environment (default ``5000``) and
binds to ``0.0.0.0`` so the desktop client running on the same machine can
reach it via ``http://localhost:<PORT>``. For production, gunicorn imports
``wsgi:app`` instead.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


def main() -> None:
    # Load ``server/.env`` before the factory runs so Config picks up vars.
    load_dotenv()

    # Imported lazily so ``load_dotenv`` runs first.
    from app import create_app

    app = create_app()
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_ENV", "development").strip().lower() == "development"

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()

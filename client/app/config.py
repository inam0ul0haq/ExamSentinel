"""
ExamSentinel client configuration.
Reads settings from environment variables (loaded from ``client/.env`` when present).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the *client* directory (one level above this file's package).
_CLIENT_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _CLIENT_DIR / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE)

# ---------------------------------------------------------------------------
# Public configuration values
# ---------------------------------------------------------------------------

API_BASE_URL: str = os.getenv(
    "API_BASE_URL", "https://web-production-5a17d.up.railway.app/api/v1"
).rstrip("/")

SKIP_VM_CHECK: bool = os.getenv("SKIP_VM_CHECK", "0").strip().lower() in (
    "1", "true", "yes",
)

REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))

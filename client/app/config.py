"""
ExamSentinel client configuration.
Reads settings from environment variables (loaded from ``client/.env`` when present).

PyInstaller-aware: when frozen, looks for .env next to the exe first.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Determine base directory:
#   Frozen (PyInstaller onefile): directory containing the .exe
#   Source:                       client/ (one level above this package)
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent

_ENV_FILE = _BASE_DIR / ".env"
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

SKIP_STEALTH_CHECK: bool = os.getenv("SKIP_STEALTH_CHECK", "0").strip().lower() in (
    "1", "true", "yes",
)

SKIP_LOCKDOWN: bool = os.getenv("SKIP_LOCKDOWN", "0").strip().lower() in (
    "1", "true", "yes",
)

REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))

"""Runtime configuration, read from environment variables.

Defaults suit local development (DB at project root). The Docker image sets
DATA_DIR=/data so the database and backups live on a mounted volume.
"""
import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

DATA_DIR = Path(os.environ.get("DATA_DIR") or APP_DIR.parent)
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'expenses.db'}"

# Set to true when served over HTTPS (e.g. behind a reverse proxy).
COOKIE_SECURE = _env_bool("COOKIE_SECURE", False)
SESSION_TTL_DAYS = _env_int("SESSION_TTL_DAYS", 30)

# Initial admin account, only used when the database has no users yet.
# Without ADMIN_PASSWORD the admin starts with "changeme" and must change it on first login.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME") or "admin"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or None
DEFAULT_ADMIN_PASSWORD = "changeme"

# Login throttling: max failed attempts per (client, username) within the window.
LOGIN_MAX_FAILURES = _env_int("LOGIN_MAX_FAILURES", 5)
LOGIN_WINDOW_SECONDS = _env_int("LOGIN_WINDOW_SECONDS", 15 * 60)

# Daily SQLite backups into DATA_DIR/backups. 0 disables.
BACKUP_KEEP = _env_int("BACKUP_KEEP", 14)
BACKUP_DIR = DATA_DIR / "backups"

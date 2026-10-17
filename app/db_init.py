"""Schema creation, lightweight migrations, admin seeding and backups.

Migrations are additive and idempotent: create_all() builds missing tables for a
fresh database, and _COLUMN_MIGRATIONS adds columns to databases created by
older versions. PRAGMA user_version records the schema version.
"""
import datetime
import logging
import sqlite3
from pathlib import Path

from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from app import config, models
from app.app_settings import DEFAULTS
from app.auth import hash_password
from app.database import Base

log = logging.getLogger("app")

SCHEMA_VERSION = 2

# (table, column, DDL used for ALTER TABLE ... ADD COLUMN)
_COLUMN_MIGRATIONS = [
    ("users", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0"),
]


def migrate(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, column, ddl in _COLUMN_MIGRATIONS:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                log.info("Migrating: adding %s.%s", table, column)
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")


def seed(db: Session) -> None:
    if not db.query(models.User).first():
        password = config.ADMIN_PASSWORD or config.DEFAULT_ADMIN_PASSWORD
        db.add(models.User(
            name=config.ADMIN_USERNAME,
            password_hash=hash_password(password),
            is_admin=True,
            must_change_password=config.ADMIN_PASSWORD is None,
        ))
        log.warning(
            "Created initial admin '%s'%s", config.ADMIN_USERNAME,
            "" if config.ADMIN_PASSWORD else f" with password '{config.DEFAULT_ADMIN_PASSWORD}' (change it on first login)",
        )
    for key, value in DEFAULTS.items():
        if db.get(models.AppSetting, key) is None:
            db.add(models.AppSetting(key=key, value=value))
    db.commit()


def sqlite_path(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url == prefix:
        return None
    return Path(database_url[len(prefix):])


def backup_database(db_path: Path, backup_dir: Path, keep: int) -> Path | None:
    """Copy the live SQLite DB using the online backup API and prune old copies."""
    if keep <= 0 or not db_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    target = backup_dir / f"expenses-{stamp}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    backups = sorted(backup_dir.glob("expenses-*.db"))
    for old in backups[:-keep]:
        old.unlink()
    return target

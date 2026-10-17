from sqlalchemy.orm import Session

from app import models

DEFAULTS = {
    "settlement_mode": "simplified",
    "currency": "EUR",
}


def get_setting(db: Session, key: str) -> str:
    row = db.get(models.AppSetting, key)
    return row.value if row else DEFAULTS[key]


def get_all_settings(db: Session) -> dict[str, str]:
    return {key: get_setting(db, key) for key in DEFAULTS}


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(models.AppSetting, key)
    if row is None:
        db.add(models.AppSetting(key=key, value=value))
    else:
        row.value = value

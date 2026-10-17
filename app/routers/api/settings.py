from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.app_settings import get_all_settings, set_setting
from app.auth import get_current_user, get_db, require_admin

router = APIRouter()


@router.get("/", response_model=schemas.SettingsRead)
def get_settings(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return get_all_settings(db)


@router.patch("/", response_model=schemas.SettingsRead)
def update_settings(
    payload: schemas.SettingsUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    for key, value in payload.model_dump(exclude_none=True).items():
        set_setting(db, key, value)
    db.commit()
    return get_all_settings(db)

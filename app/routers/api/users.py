from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import (
    SESSION_COOKIE_NAME,
    delete_user_sessions,
    get_current_user,
    get_db,
    hash_password,
    require_admin,
    verify_password,
)

router = APIRouter()

_NAME_TAKEN = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User name already exists")


def _get_user_or_404(db: Session, user_id: int) -> models.User:
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _active_admin_count(db: Session) -> int:
    return db.query(models.User).filter(models.User.is_admin.is_(True), models.User.is_active.is_(True)).count()


@router.post(
    "/",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "User name already exists"}},
)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    db_user = models.User(
        name=user.name,
        password_hash=hash_password(user.password),
        is_admin=False,
        is_active=True,
        # The admin picks a temporary password; the user sets their own on first login.
        must_change_password=True,
    )
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _NAME_TAKEN
    db.refresh(db_user)
    return db_user


@router.get("/", response_model=list[schemas.UserRead])
def list_users(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    return db.query(models.User).order_by(models.User.name).all()


@router.get("/me", response_model=schemas.UserRead)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get(
    "/{user_id}",
    response_model=schemas.UserRead,
    responses={
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
    },
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return _get_user_or_404(db, user_id)


@router.patch(
    "/{user_id}",
    response_model=schemas.UserRead,
    responses={
        400: {"description": "Current password wrong"},
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
        409: {"description": "User name already exists / last admin"},
    },
)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    is_self = current_user.id == user_id
    if not current_user.is_admin and not is_self:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    user = _get_user_or_404(db, user_id)

    if (payload.is_admin is not None or payload.is_active is not None) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")

    if payload.is_admin is False and user.is_admin and user.is_active and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove the last admin")

    if payload.is_active is False:
        if is_self:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot deactivate yourself")
        if user.is_admin and user.is_active and _active_admin_count(db) <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot deactivate the last admin")

    if payload.password is not None and is_self:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is wrong")

    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            delete_user_sessions(db, user.id)
    if payload.name is not None:
        user.name = payload.name
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        if is_self:
            user.must_change_password = False
            delete_user_sessions(db, user.id, keep_session_id=request.cookies.get(SESSION_COOKIE_NAME))
        else:
            # Admin reset: the user must pick a new password at next login.
            user.must_change_password = True
            delete_user_sessions(db, user.id)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _NAME_TAKEN
    db.refresh(user)
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
        409: {"description": "User has expenses / last admin"},
    },
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete yourself")
    user = _get_user_or_404(db, user_id)
    if user.is_admin and user.is_active and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete the last admin")
    # Deleting shares would break expenses (they must net to zero) and silently erase debts.
    if db.query(models.ExpenseShare).filter(models.ExpenseShare.user_id == user_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User has expenses. Deactivate the user instead.",
        )
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

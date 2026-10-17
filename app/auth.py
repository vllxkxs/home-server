import datetime
import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import config, models
from app.database import SessionLocal

SESSION_COOKIE_NAME = "session_id"
SESSION_TTL_DAYS = config.SESSION_TTL_DAYS
# Only write a new expiry when it moved by at least this much, to avoid a DB write per request.
_SESSION_REFRESH_INTERVAL = datetime.timedelta(hours=1)

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")
# Used to spend the same hashing time when a login name does not exist.
_DUMMY_HASH = pwd_context.hash("dummy-password")


def utcnow() -> datetime.datetime:
    # Naive UTC: SQLite stores datetimes without timezone.
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        pwd_context.verify(password, _DUMMY_HASH)
        return False
    return pwd_context.verify(password, password_hash)


def create_session(db: Session, user: models.User) -> models.UserSession:
    now = utcnow()
    session = models.UserSession(
        session_id=secrets.token_urlsafe(32),
        user_id=user.id,
        created_at=now,
        expires_at=now + datetime.timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, httponly=True, samesite="lax", secure=config.COOKIE_SECURE,
    )


def delete_user_sessions(db: Session, user_id: int, keep_session_id: str | None = None) -> None:
    query = db.query(models.UserSession).filter(models.UserSession.user_id == user_id)
    if keep_session_id:
        query = query.filter(models.UserSession.session_id != keep_session_id)
    query.delete(synchronize_session=False)


def get_current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> models.User:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = (
        db.query(models.UserSession)
        .filter(models.UserSession.session_id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    now = utcnow()
    if session.expires_at < now or not session.user.is_active:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    # Rolling session: extend expiry and refresh cookie.
    new_expiry = now + datetime.timedelta(days=SESSION_TTL_DAYS)
    if new_expiry - session.expires_at >= _SESSION_REFRESH_INTERVAL:
        session.expires_at = new_expiry
        db.commit()
        set_session_cookie(response, session.session_id)

    return session.user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user

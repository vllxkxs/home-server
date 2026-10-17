import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.auth import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    create_session,
    get_current_user,
    get_db,
    set_session_cookie,
    utcnow,
    verify_password,
)

router = APIRouter()


class LoginThrottle:
    """In-memory sliding window of failed logins per (client address, username)."""

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: tuple[str, str], now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        return attempts

    def retry_after(self, key: tuple[str, str]) -> int:
        """Seconds until the next attempt is allowed, 0 if allowed now."""
        now = time.monotonic()
        with self._lock:
            attempts = self._recent(key, now)
            if not attempts:
                del self._failures[key]
                return 0
            if len(attempts) < self.max_failures:
                return 0
            return max(1, int(attempts[0] + self.window - now))

    def record_failure(self, key: tuple[str, str]) -> None:
        now = time.monotonic()
        with self._lock:
            self._recent(key, now).append(now)

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_throttle = LoginThrottle(config.LOGIN_MAX_FAILURES, config.LOGIN_WINDOW_SECONDS)


@router.post("/login", response_model=schemas.UserRead, responses={429: {"description": "Too many attempts"}})
def login(payload: schemas.LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    key = (request.client.host if request.client else "unknown", payload.name.strip().lower())
    wait = login_throttle.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {wait // 60 + 1} min.",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(models.User).filter(models.User.name == payload.name.strip()).first()
    if not verify_password(payload.password, user.password_hash if user else None) or not user.is_active:
        login_throttle.record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    login_throttle.reset(key)
    db.query(models.UserSession).filter(models.UserSession.expires_at < utcnow()).delete(synchronize_session=False)
    session = create_session(db, user)
    set_session_cookie(response, session.session_id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        db.query(models.UserSession).filter(models.UserSession.session_id == session_id).delete()
        db.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response

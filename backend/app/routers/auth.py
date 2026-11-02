from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.auth.dependencies import get_current_user
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import hash_token
from app.database import get_db
from app.models import RefreshToken, SecurityEventType, User
from app.schemas.auth import LoginRequest, MessageResponse, SignupRequest, UserResponse
from app.services.analytics import track_event
from app.services.security_log import log_security_event
from app.services.sessions import issue_tokens, revoke_family

router = APIRouter(prefix="/auth", tags=["auth"])

SIGNUP_MESSAGE = "If this email can be registered, you will receive a confirmation email shortly."
LOGIN_FAILED_MESSAGE = "Invalid email or password."
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

_DUMMY_PASSWORD_HASH = hash_password("timing-equalizer-not-a-real-password")


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> MessageResponse:
    password_hash = hash_password(payload.password)

    email_taken = db.scalar(select(User.id).where(User.email == payload.email))
    if email_taken:
        return MessageResponse(message=SIGNUP_MESSAGE)

    user = User(email=payload.email, password_hash=password_hash)
    db.add(user)
    try:
        db.flush()
        track_event(db, user.id, "user_signed_up")
        db.commit()
    except IntegrityError:
        db.rollback()

    return MessageResponse(message=SIGNUP_MESSAGE)


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.email == payload.email))

    if user is None or user.password_hash is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        log_security_event(db, request, SecurityEventType.LOGIN_FAILED)
        db.commit()
        raise _unauthorized(LOGIN_FAILED_MESSAGE)

    if user.locked_until and user.locked_until > now:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        log_security_event(db, request, SecurityEventType.LOGIN_FAILED, user.id)
        db.commit()
        raise _unauthorized(LOGIN_FAILED_MESSAGE)

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        log_security_event(db, request, SecurityEventType.LOGIN_FAILED, user.id)
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCKOUT_DURATION
            user.failed_login_count = 0
            log_security_event(db, request, SecurityEventType.ACCOUNT_LOCKED, user.id)
        db.commit()
        raise _unauthorized(LOGIN_FAILED_MESSAGE)

    user.failed_login_count = 0
    user.locked_until = None
    access_token, refresh_token = issue_tokens(db, user.id)
    log_security_event(db, request, SecurityEventType.LOGIN_SUCCESS, user.id)
    db.commit()

    set_auth_cookies(response, access_token, refresh_token)
    return user


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> None:
    if not refresh_token:
        raise _unauthorized()

    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    if stored is None:
        raise _unauthorized()

    if stored.revoked_at is not None:
        revoke_family(db, stored.family_id)
        log_security_event(db, request, SecurityEventType.REFRESH_TOKEN_REUSED, stored.user_id)
        db.commit()
        raise _unauthorized()

    now = datetime.now(timezone.utc)
    if stored.expires_at <= now:
        raise _unauthorized()

    stored.revoked_at = now
    access_token, new_refresh_token = issue_tokens(db, stored.user_id, stored.family_id)
    db.commit()

    set_auth_cookies(response, access_token, new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> None:
    if refresh_token:
        stored = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
        )
        if stored is not None:
            revoke_family(db, stored.family_id)
            db.commit()

    clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user

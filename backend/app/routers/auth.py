from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.auth.dependencies import get_current_user
from app.auth.reauth import confirm_password
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import hash_token
from app.database import get_db
from app.mailer import templates
from app.mailer.sender import EmailSender, get_email_sender, send_quietly
from app.models import RefreshToken, SecurityEventType, TokenPurpose, User
from app.schemas.account import ConfirmEmailChangeRequest, VerifyEmailRequest
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    UserResponse,
)
from app.security.rate_limit import (
    email_token_limiter,
    login_limiter,
    refresh_limiter,
    sensitive_limiter,
    signup_limiter,
)
from app.services.analytics import track_event
from app.services.email_tokens import (
    RESET_PASSWORD_LIFETIME,
    VERIFY_EMAIL_LIFETIME,
    consume_email_token,
    issue_email_token,
)
from app.services.security_log import log_security_event
from app.services.sessions import family_of, issue_tokens, revoke_all_sessions, revoke_family

router = APIRouter(prefix="/auth", tags=["auth"])

SIGNUP_MESSAGE = "If this email can be registered, you will receive a confirmation email shortly."
LOGIN_FAILED_MESSAGE = "Invalid email or password."
INVALID_LINK_MESSAGE = "This link is invalid or has expired."
FORGOT_PASSWORD_MESSAGE = "If an account uses this email, we sent it a link to reset the password."
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

_DUMMY_PASSWORD_HASH = hash_password("timing-equalizer-not-a-real-password")


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@router.post(
    "/signup",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    dependencies=[Depends(signup_limiter)],
)
def signup(
    payload: SignupRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    password_hash = hash_password(payload.password)

    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        message = templates.signup_attempt_for_existing_account(existing.email)
        background_tasks.add_task(send_quietly, sender, message)
        return MessageResponse(message=SIGNUP_MESSAGE)

    user = User(email=payload.email, password_hash=password_hash)
    db.add(user)
    try:
        db.flush()
        token = issue_email_token(db, user.id, TokenPurpose.VERIFY_EMAIL, VERIFY_EMAIL_LIFETIME)
        track_event(db, user.id, "user_signed_up")
        db.commit()
    except IntegrityError:
        db.rollback()
        return MessageResponse(message=SIGNUP_MESSAGE)

    background_tasks.add_task(send_quietly, sender, templates.verify_email(payload.email, token))
    return MessageResponse(message=SIGNUP_MESSAGE)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    dependencies=[Depends(email_token_limiter)],
)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> MessageResponse:
    stored = consume_email_token(db, payload.token, TokenPurpose.VERIFY_EMAIL)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK_MESSAGE)

    user = db.get(User, stored.user_id)
    user.is_email_verified = True
    db.commit()
    return MessageResponse(message="Your email is confirmed.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(email_token_limiter)],
)
def resend_verification(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    if user.is_email_verified:
        return MessageResponse(message="Your email is already confirmed.")

    token = issue_email_token(db, user.id, TokenPurpose.VERIFY_EMAIL, VERIFY_EMAIL_LIFETIME)
    db.commit()
    background_tasks.add_task(send_quietly, sender, templates.verify_email(user.email, token))
    return MessageResponse(message="We sent you a new confirmation link.")


@router.post("/login", response_model=UserResponse, dependencies=[Depends(login_limiter)])
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


@router.post(
    "/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(refresh_limiter)],
)
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


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    dependencies=[Depends(email_token_limiter)],
)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is not None and user.password_hash is not None:
        token = issue_email_token(db, user.id, TokenPurpose.RESET_PASSWORD, RESET_PASSWORD_LIFETIME)
        log_security_event(db, request, SecurityEventType.PASSWORD_RESET_REQUESTED, user.id)
        db.commit()
        background_tasks.add_task(send_quietly, sender, templates.password_reset(user.email, token))
    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(email_token_limiter)],
)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    stored = consume_email_token(db, payload.token, TokenPurpose.RESET_PASSWORD)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK_MESSAGE)

    user = db.get(User, stored.user_id)
    user.password_hash = hash_password(payload.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    user.is_email_verified = True
    revoke_all_sessions(db, user.id)
    log_security_event(db, request, SecurityEventType.PASSWORD_CHANGED, user.id)
    db.commit()

    clear_auth_cookies(response)
    background_tasks.add_task(send_quietly, sender, templates.password_changed(user.email))
    return MessageResponse(message="Your password was changed. Please log in again.")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    dependencies=[Depends(sensitive_limiter)],
)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> MessageResponse:
    confirm_password(db, request, user, payload.current_password)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"field": "new_password", "message": "Choose a password you are not using now"}],
        )

    user.password_hash = hash_password(payload.new_password)
    revoke_all_sessions(db, user.id, keep_family=family_of(db, refresh_token))
    log_security_event(db, request, SecurityEventType.PASSWORD_CHANGED, user.id)
    db.commit()

    background_tasks.add_task(send_quietly, sender, templates.password_changed(user.email))
    return MessageResponse(message="Your password was changed. Other devices were logged out.")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    revoke_all_sessions(db, user.id)
    log_security_event(db, request, SecurityEventType.SESSIONS_REVOKED, user.id)
    db.commit()
    clear_auth_cookies(response)


@router.post(
    "/confirm-email-change",
    response_model=MessageResponse,
    dependencies=[Depends(email_token_limiter)],
)
def confirm_email_change(
    payload: ConfirmEmailChangeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    stored = consume_email_token(db, payload.token, TokenPurpose.CHANGE_EMAIL)
    if stored is None or stored.new_email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK_MESSAGE)

    user = db.get(User, stored.user_id)
    old_email = user.email
    user.email = stored.new_email
    user.is_email_verified = True
    log_security_event(db, request, SecurityEventType.EMAIL_CHANGED, user.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK_MESSAGE
        ) from None

    background_tasks.add_task(send_quietly, sender, templates.email_changed(old_email, user.email))
    return MessageResponse(message="Your email address was changed.")

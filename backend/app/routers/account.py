from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.cookies import clear_auth_cookies
from app.auth.dependencies import get_current_user
from app.auth.reauth import confirm_password
from app.database import get_db
from app.mailer import templates
from app.mailer.sender import EmailSender, get_email_sender, send_quietly
from app.models import SecurityEventType, TokenPurpose, User
from app.schemas.account import (
    ChangeEmailRequest,
    DeleteAccountRequest,
    NotificationSettings,
    NotificationSettingsUpdate,
)
from app.schemas.auth import MessageResponse
from app.security.rate_limit import export_limiter, sensitive_limiter, write_limiter
from app.services.email_tokens import CHANGE_EMAIL_LIFETIME, issue_email_token
from app.services.export import export_user_data
from app.services.security_log import log_security_event

router = APIRouter(prefix="/me", tags=["account"])


def _settings_of(user: User) -> NotificationSettings:
    return NotificationSettings(email_enabled=user.notify_email, day_before=user.notify_day_before)


@router.get("/notifications", response_model=NotificationSettings)
def get_notification_settings(user: User = Depends(get_current_user)) -> NotificationSettings:
    return _settings_of(user)


@router.patch(
    "/notifications",
    response_model=NotificationSettings,
    dependencies=[Depends(write_limiter)],
)
def update_notification_settings(
    payload: NotificationSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationSettings:
    if payload.email_enabled is not None:
        user.notify_email = payload.email_enabled
    if payload.day_before is not None:
        user.notify_day_before = payload.day_before
    db.commit()
    return _settings_of(user)


@router.post("/email", response_model=MessageResponse, dependencies=[Depends(sensitive_limiter)])
def request_email_change(
    payload: ChangeEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    confirm_password(db, request, user, payload.password)
    if payload.new_email == user.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"field": "new_email", "message": "This is already your email address"}],
        )

    taken = db.scalar(select(User.id).where(User.email == payload.new_email))
    if taken is None:
        token = issue_email_token(
            db, user.id, TokenPurpose.CHANGE_EMAIL, CHANGE_EMAIL_LIFETIME, new_email=payload.new_email
        )
        log_security_event(db, request, SecurityEventType.EMAIL_CHANGE_REQUESTED, user.id)
        db.commit()
        message = templates.confirm_new_email(payload.new_email, token)
        background_tasks.add_task(send_quietly, sender, message)

    return MessageResponse(
        message="If this address can be used, we sent a confirmation link to it."
    )


@router.post(
    "/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(sensitive_limiter)],
)
def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> None:
    confirm_password(db, request, user, payload.password)
    email = user.email

    log_security_event(db, request, SecurityEventType.ACCOUNT_DELETED, user.id)
    db.flush()
    db.delete(user)
    db.commit()

    clear_auth_cookies(response)
    background_tasks.add_task(send_quietly, sender, templates.account_deleted(email))


@router.get("/export", dependencies=[Depends(export_limiter)])
def export_my_data(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    today = datetime.now(timezone.utc).date().isoformat()
    return JSONResponse(
        content=jsonable_encoder(export_user_data(db, user)),
        headers={"Content-Disposition": f'attachment; filename="my-world-export-{today}.json"'},
    )

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.account import NotificationSettings, NotificationSettingsUpdate
from app.security.rate_limit import write_limiter

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

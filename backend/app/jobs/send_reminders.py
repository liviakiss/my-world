import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.mailer import templates
from app.mailer.sender import EmailError, EmailSender, get_email_sender
from app.models import (
    DatePrecision, Follow, Notification, NotificationKind, Release, User, Work,
)
from app.services.analytics import track_event
from app.services.follows import upcoming_for

logger = logging.getLogger(__name__)

ANNOUNCEMENT_WINDOW = timedelta(hours=26)


@dataclass
class ReminderResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0


def _release_key(label: str, release_date: date) -> str:
    return f"{label}|{release_date.isoformat()}"[:300]


def _already_sent(db: Session, user: User, work_id, kind: NotificationKind, key: str) -> bool:
    return (
        db.scalar(
            select(Notification.id).where(
                Notification.user_id == user.id,
                Notification.work_id == work_id,
                Notification.kind == kind,
                Notification.release_key == key,
            )
        )
        is not None
    )


def _send_once(
    db: Session,
    sender: EmailSender,
    result: ReminderResult,
    user: User,
    work: Work,
    kind: NotificationKind,
    label: str,
    release_date: date,
) -> None:
    key = _release_key(label, release_date)
    if _already_sent(db, user, work.id, kind, key):
        result.skipped += 1
        return

    message = templates.release_reminder(user.email, kind, work.title, label, release_date)
    try:
        sender.send(message)
    except EmailError as exc:
        logger.warning("Reminder for work %s failed: %s", work.id, exc)
        result.failed += 1
        return

    db.add(Notification(user_id=user.id, work_id=work.id, kind=kind, release_key=key))
    track_event(db, user.id, "reminder_sent", media_type=work.media_type.value, kind=kind.value)
    db.commit()
    result.sent += 1


def _eligible_users(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.is_email_verified.is_(True),
                User.notify_email.is_(True),
                User.id.in_(select(Follow.user_id)),
            )
            .order_by(User.id)
        ).all()
    )


def _date_reminders(
    db: Session, sender: EmailSender, result: ReminderResult, user: User, today: date
) -> None:
    due = {today: NotificationKind.RELEASE_DAY}
    if user.notify_day_before:
        due[today + timedelta(days=1)] = NotificationKind.DAY_BEFORE

    for item in upcoming_for(db, user.id, today):
        kind = due.get(item.release_date)
        if kind is None or item.precision != DatePrecision.DAY:
            continue
        work = db.get(Work, item.work.id)
        _send_once(db, sender, result, user, work, kind, item.label, item.release_date)


def _announcements(
    db: Session, sender: EmailSender, result: ReminderResult, user: User, now: datetime
) -> None:
    rows = db.execute(
        select(Release, Work)
        .join(Work, Work.id == Release.work_id)
        .join(Follow, Follow.work_id == Release.work_id)
        .where(
            Follow.user_id == user.id,
            Release.updated_at >= now - ANNOUNCEMENT_WINDOW,
            Release.release_date > now.date(),
            Release.precision == DatePrecision.DAY,
        )
        .order_by(Release.release_date)
    ).all()
    for release, work in rows:
        _send_once(
            db, sender, result, user, work, NotificationKind.ANNOUNCED,
            release.label, release.release_date,
        )


def send_reminders(db: Session, sender: EmailSender, now: datetime | None = None) -> ReminderResult:
    now = now or datetime.now(timezone.utc)
    result = ReminderResult()
    for user in _eligible_users(db):
        _announcements(db, sender, result, user, now)
        _date_reminders(db, sender, result, user, now.date())
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        result = send_reminders(db, get_email_sender())
    logger.info("Reminders finished: %s", result)


if __name__ == "__main__":
    main()

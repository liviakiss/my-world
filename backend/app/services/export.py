from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from app.models import AnalyticsEvent, Entry, Follow, Notification, SecurityEvent, User, Work


def _work(work: Work) -> dict[str, Any]:
    return {
        "title": work.title,
        "media_type": work.media_type,
        "source": work.source,
        "total_units": work.total_units,
    }


def export_user_data(db: Session, user: User) -> dict[str, Any]:
    entries = db.scalars(
        select(Entry)
        .join(Entry.work)
        .options(contains_eager(Entry.work))
        .where(Entry.user_id == user.id)
        .order_by(Entry.created_at)
    ).all()
    custom_works = db.scalars(
        select(Work).where(Work.created_by_user_id == user.id).order_by(Work.created_at)
    ).all()
    follows = db.scalars(
        select(Follow)
        .join(Follow.work)
        .options(contains_eager(Follow.work))
        .where(Follow.user_id == user.id)
        .order_by(Follow.created_at)
    ).all()
    notifications = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.sent_at)
    ).all()
    security_events = db.scalars(
        select(SecurityEvent)
        .where(SecurityEvent.user_id == user.id)
        .order_by(SecurityEvent.created_at)
    ).all()
    analytics_events = db.scalars(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user.id)
        .order_by(AnalyticsEvent.created_at)
    ).all()

    return {
        "exported_at": datetime.now(timezone.utc),
        "account": {
            "email": user.email,
            "email_verified": user.is_email_verified,
            "created_at": user.created_at,
            "notifications": {
                "email_enabled": user.notify_email,
                "day_before": user.notify_day_before,
            },
        },
        "shelf": [
            {
                "work": _work(entry.work),
                "status": entry.status,
                "progress": entry.progress,
                "rating": entry.rating,
                "notes": entry.notes,
                "started_on": entry.started_on,
                "finished_on": entry.finished_on,
                "added_at": entry.created_at,
            }
            for entry in entries
        ],
        "custom_works": [
            {**_work(work), "description": work.description, "creators": work.creators, "genres": work.genres}
            for work in custom_works
        ],
        "follows": [
            {
                "work": _work(follow.work),
                "my_release_date": follow.manual_release_date,
                "my_release_label": follow.manual_release_label,
                "followed_at": follow.created_at,
            }
            for follow in follows
        ],
        "reminders_sent": [
            {"kind": notification.kind, "release": notification.release_key, "sent_at": notification.sent_at}
            for notification in notifications
        ],
        "security_events": [
            {"type": event.event_type, "user_agent": event.user_agent, "at": event.created_at}
            for event in security_events
        ],
        "activity_events": [
            {"type": event.event_type, "details": event.properties, "at": event.created_at}
            for event in analytics_events
        ],
    }

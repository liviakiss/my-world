import uuid

from sqlalchemy.orm import Session

from app.models import EVENT_TYPES, AnalyticsEvent


def track_event(db: Session, user_id: uuid.UUID, event_type: str, **properties) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown analytics event: {event_type}")
    db.add(AnalyticsEvent(user_id=user_id, event_type=event_type, properties=properties))

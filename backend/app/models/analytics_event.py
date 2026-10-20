# analytics_event.py — product analytics: what users DO in the app.
# Feeds: personal stats page, admin product dashboard, the pandas case study.
#
# PRIVACY RULE: properties may contain types and counts (media_type, status),
# NEVER titles, notes, emails or anything that identifies a person or their taste.
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Allowed event types live in CODE, not in the database:
# adding a new one = add a line here, no migration needed.
EVENT_TYPES = {
    "user_signed_up",
    "item_added",
    "status_changed",
    "item_finished",
    "rating_set",
    "series_followed",
    "release_found",
    "reminder_sent",
    "spin_wheel_used",
}


class AnalyticsEvent(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # CASCADE: when a user deletes their account, all their analytics go too (GDPR promise).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    event_type: Mapped[str] = mapped_column(String(50))

    # Flexible details, e.g. {"media_type": "book", "from": "want", "to": "in_progress"}
    # JSONB = binary JSON in Postgres: can be filtered and indexed in SQL.
    properties: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # COMPOSITE index: one index on TWO columns, in this order.
    # Most dashboard queries look like:
    #   "count item_finished events per week in the last 3 months"
    # → filter by event_type first, then by a time range.
    __table_args__ = (
        Index("ix_events_type_created_at", "event_type", "created_at"),
    )
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import enum_values


class NotificationKind(str, enum.Enum):
    ANNOUNCED = "announced"
    DAY_BEFORE = "day_before"
    RELEASE_DAY = "release_day"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, native_enum=False, length=20, values_callable=enum_values)
    )
    release_key: Mapped[str] = mapped_column(String(300))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "work_id", "kind", "release_key", name="uq_notifications_once"
        ),
    )

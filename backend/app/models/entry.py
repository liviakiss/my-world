import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric,
    Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import EntryStatus, enum_values
from app.models.work import Work

NOTES_MAX_LENGTH = 5000


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("works.id"), index=True)

    status: Mapped[EntryStatus] = mapped_column(
        Enum(EntryStatus, native_enum=False, length=20, values_callable=enum_values),
        default=EntryStatus.WANT,
        server_default=EntryStatus.WANT.value,
    )

    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    notes: Mapped[str | None] = mapped_column(Text)

    started_on: Mapped[date | None] = mapped_column(Date)
    finished_on: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    work: Mapped[Work] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "work_id", name="uq_entries_user_work"),
        Index("ix_entries_user_status", "user_id", "status"),
        CheckConstraint("progress >= 0", name="ck_entries_progress_not_negative"),
        CheckConstraint(
            "rating IS NULL OR (rating BETWEEN 0.5 AND 5 AND rating * 2 = floor(rating * 2))",
            name="ck_entries_rating_half_stars",
        ),
        CheckConstraint(
            f"notes IS NULL OR char_length(notes) <= {NOTES_MAX_LENGTH}",
            name="ck_entries_notes_length",
        ),
        CheckConstraint(
            "finished_on IS NULL OR started_on IS NULL OR finished_on >= started_on",
            name="ck_entries_dates_in_order",
        ),
    )

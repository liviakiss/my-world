import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import DatePrecision, enum_values
from app.models.work import Work

MANUAL_LABEL_MAX_LENGTH = 200


class Follow(Base):
    __tablename__ = "follows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), index=True
    )

    manual_release_date: Mapped[date | None] = mapped_column(Date)
    manual_release_label: Mapped[str | None] = mapped_column(String(MANUAL_LABEL_MAX_LENGTH))
    manual_release_precision: Mapped[DatePrecision] = mapped_column(
        Enum(DatePrecision, native_enum=False, length=20, values_callable=enum_values),
        default=DatePrecision.DAY,
        server_default=DatePrecision.DAY.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    work: Mapped[Work] = relationship()

    __table_args__ = (UniqueConstraint("user_id", "work_id", name="uq_follows_user_work"),)

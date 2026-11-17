import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import DataSource, DatePrecision, enum_values


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"))

    label: Mapped[str] = mapped_column(String(200))
    release_date: Mapped[date | None] = mapped_column(Date)
    precision: Mapped[DatePrecision] = mapped_column(
        Enum(DatePrecision, native_enum=False, length=20, values_callable=enum_values)
    )
    source: Mapped[DataSource] = mapped_column(
        Enum(DataSource, native_enum=False, length=20, values_callable=enum_values)
    )

    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("work_id", "label", name="uq_releases_work_label"),
        Index("ix_releases_work_date", "work_id", "release_date"),
    )

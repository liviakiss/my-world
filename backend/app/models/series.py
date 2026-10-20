# series.py — groups Works in reading/watching order.
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MediaType, SeriesStatus, enum_values


class Series(Base):
    __tablename__ = "series"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))

    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=20, values_callable=enum_values)
    )

    # ONGOING series are the ones the daily release job checks.
    status: Mapped[SeriesStatus] = mapped_column(
        Enum(SeriesStatus, native_enum=False, length=20, values_callable=enum_values),
        default=SeriesStatus.UNKNOWN,
        server_default=SeriesStatus.UNKNOWN.value,
        index=True,   # the release job asks: "give me all ONGOING series"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationship(): lets Python do series.works instead of writing a query.
    # It does NOT create a column; the real link is Work.series_id.
    works: Mapped[list["Work"]] = relationship(back_populates="series")
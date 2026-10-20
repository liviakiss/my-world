# work.py — one book / manga / show / movie / anime / game.
# Shared catalogue data: NO personal information in this table.
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import DataSource, DatePrecision, MediaType, enum_values


class Work(Base):
    __tablename__ = "works"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=20, values_callable=enum_values),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))

    # SECURITY: text from external APIs is stored and shown as PLAIN TEXT only,
    # never rendered as HTML (prevents XSS through a malicious description).
    description: Mapped[str | None] = mapped_column(Text)

    # SECURITY: only https URLs from allowed image hosts will be accepted
    # (checked in code when saving), so nobody can inject a tracking or malicious URL.
    cover_url: Mapped[str | None] = mapped_column(String(1000))

    # Lists from the API, e.g. ["Fantasy", "Adventure"] — flexible, queryable.
    creators: Mapped[list] = mapped_column(JSONB, server_default="[]")
    genres: Mapped[list] = mapped_column(JSONB, server_default="[]")

    # Size of the work, for progress %: pages, episodes, chapters, hours.
    total_units: Mapped[int | None] = mapped_column(Integer)

    release_date: Mapped[date | None] = mapped_column(Date)
    release_date_precision: Mapped[DatePrecision] = mapped_column(
        Enum(DatePrecision, native_enum=False, length=20, values_callable=enum_values),
        default=DatePrecision.UNKNOWN,
        server_default=DatePrecision.UNKNOWN.value,
    )

    # WHERE the data came from + that source's own ID ("tmdb", "1234").
    source: Mapped[DataSource] = mapped_column(
        Enum(DataSource, native_enum=False, length=20, values_callable=enum_values)
    )
    external_id: Mapped[str | None] = mapped_column(String(100))

    # Custom works (typed by a user) are PRIVATE to that user.
    # NULL for works from public APIs. CASCADE: delete the user → their custom works go too.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Position in its series. Numeric, not Float: 1.5 (a novella between books 1 and 2)
    # must stay exactly 1.5 — Float can turn it into 1.4999999.
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), index=True
    )
    series_position: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    series: Mapped["Series | None"] = relationship(back_populates="works")

    __table_args__ = (
        # The same API item can only be cached ONCE (no duplicate "Frieren" rows).
        UniqueConstraint("source", "external_id", name="uq_works_source_external_id"),
    )
import uuid
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Entry, EntryStatus, Work
from app.schemas.stats import (
    Backlog,
    MediaTypeTotal,
    MonthCount,
    PersonalStats,
    RatingBucket,
    StatusTotals,
)

RATING_STEPS = [Decimal(step) / 2 for step in range(1, 11)]

FINISHED_PER_MONTH_SQL = text(
    """
    WITH months AS (
        SELECT generate_series(
            date_trunc('month', CURRENT_DATE) - INTERVAL '11 months',
            date_trunc('month', CURRENT_DATE),
            INTERVAL '1 month'
        )::date AS month
    ),
    finished AS (
        SELECT date_trunc('month', finished_on)::date AS month, count(*) AS total
        FROM entries
        WHERE user_id = :user_id
          AND status = 'finished'
          AND finished_on IS NOT NULL
        GROUP BY 1
    )
    SELECT months.month, COALESCE(finished.total, 0) AS total
    FROM months
    LEFT JOIN finished USING (month)
    ORDER BY months.month
    """
)


def _round(value: object, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def _status_totals(db: Session, user_id: uuid.UUID) -> StatusTotals:
    counts = [func.count().filter(Entry.status == status).label(status.value) for status in EntryStatus]
    row = db.execute(
        select(func.count().label("entries"), *counts).where(Entry.user_id == user_id)
    ).one()
    return StatusTotals(**row._mapping)


def _by_media_type(db: Session, user_id: uuid.UUID) -> list[MediaTypeTotal]:
    total = func.count().label("total")
    rows = db.execute(
        select(
            Work.media_type,
            total,
            func.count().filter(Entry.status == EntryStatus.FINISHED).label("finished"),
        )
        .join(Entry.work)
        .where(Entry.user_id == user_id)
        .group_by(Work.media_type)
        .order_by(total.desc(), Work.media_type)
    )
    return [MediaTypeTotal(**row._mapping) for row in rows]


def _finished_per_month(db: Session, user_id: uuid.UUID) -> list[MonthCount]:
    rows = db.execute(FINISHED_PER_MONTH_SQL, {"user_id": user_id})
    return [MonthCount(month=row.month.strftime("%Y-%m"), count=row.total) for row in rows]


def _average_days_to_finish(db: Session, user_id: uuid.UUID) -> float | None:
    value = db.scalar(
        select(func.avg(Entry.finished_on - Entry.started_on)).where(
            Entry.user_id == user_id,
            Entry.status == EntryStatus.FINISHED,
            Entry.started_on.is_not(None),
            Entry.finished_on.is_not(None),
        )
    )
    return _round(value)


def _ratings(db: Session, user_id: uuid.UUID) -> tuple[float | None, list[RatingBucket]]:
    rows = db.execute(
        select(Entry.rating, func.count())
        .where(Entry.user_id == user_id, Entry.rating.is_not(None))
        .group_by(Entry.rating)
    ).all()
    counts = {rating: count for rating, count in rows}

    rated = sum(counts.values())
    average = sum(rating * count for rating, count in counts.items()) / rated if rated else None
    buckets = [RatingBucket(rating=float(step), count=counts.get(step, 0)) for step in RATING_STEPS]
    return _round(average, 2), buckets


def _backlog(db: Session, user_id: uuid.UUID) -> Backlog:
    age_days = func.date_part("epoch", func.now() - Entry.created_at) / 86400
    row = db.execute(
        select(func.count(), func.min(Entry.created_at), func.avg(age_days)).where(
            Entry.user_id == user_id, Entry.status == EntryStatus.WANT
        )
    ).one()
    count, oldest, average_age = row
    return Backlog(count=count, oldest_added_at=oldest, average_age_days=_round(average_age))


def personal_stats(db: Session, user_id: uuid.UUID) -> PersonalStats:
    totals = _status_totals(db, user_id)
    closed = totals.finished + totals.dropped
    average_rating, rating_distribution = _ratings(db, user_id)

    return PersonalStats(
        totals=totals,
        completion_rate=round(totals.finished / closed, 3) if closed else None,
        by_media_type=_by_media_type(db, user_id),
        finished_per_month=_finished_per_month(db, user_id),
        average_days_to_finish=_average_days_to_finish(db, user_id),
        average_rating=average_rating,
        rating_distribution=rating_distribution,
        backlog=_backlog(db, user_id),
    )

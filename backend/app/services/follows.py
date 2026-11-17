import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from app.models import DatePrecision, Follow, Release, Work
from app.schemas.follows import UpcomingRelease
from app.schemas.works import WorkSummary
from app.services.analytics import track_event

MAX_FOLLOWS_PER_USER = 500
NO_DATE_LABEL = "Date not announced yet"
MANUAL_DEFAULT_LABEL = "Next release"


def get_own_follow(db: Session, follow_id: uuid.UUID, user_id: uuid.UUID) -> Follow | None:
    return db.scalar(select(Follow).where(Follow.id == follow_id, Follow.user_id == user_id))


def count_follows(db: Session, user_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Follow).where(Follow.user_id == user_id))


def ensure_follow(db: Session, user_id: uuid.UUID, work: Work) -> None:
    already = db.scalar(
        select(Follow.id).where(Follow.user_id == user_id, Follow.work_id == work.id)
    )
    if already is not None or count_follows(db, user_id) >= MAX_FOLLOWS_PER_USER:
        return
    db.add(Follow(user_id=user_id, work=work))
    track_event(db, user_id, "series_followed", media_type=work.media_type.value, automatic=True)


def _next_releases(db: Session, work_ids: list[uuid.UUID], today: date) -> dict[uuid.UUID, Release]:
    if not work_ids:
        return {}
    releases = db.scalars(
        select(Release)
        .where(Release.work_id.in_(work_ids), Release.release_date >= today)
        .order_by(Release.release_date, Release.label)
    )
    first: dict[uuid.UUID, Release] = {}
    for release in releases:
        first.setdefault(release.work_id, release)
    return first


def _upcoming_item(follow: Follow, release: Release | None, today: date) -> UpcomingRelease:
    work = WorkSummary.model_validate(follow.work)
    manual_date = follow.manual_release_date
    if manual_date is not None and manual_date < today:
        manual_date = None

    if manual_date is not None:
        suggested = release.release_date if release and release.release_date != manual_date else None
        return UpcomingRelease(
            follow_id=follow.id,
            work=work,
            label=follow.manual_release_label or MANUAL_DEFAULT_LABEL,
            release_date=manual_date,
            precision=follow.manual_release_precision,
            source="you",
            suggested_date=suggested,
        )

    if release is not None:
        return UpcomingRelease(
            follow_id=follow.id,
            work=work,
            label=release.label,
            release_date=release.release_date,
            precision=release.precision,
            source=release.source.value,
            suggested_date=None,
        )

    return UpcomingRelease(
        follow_id=follow.id,
        work=work,
        label=follow.manual_release_label or NO_DATE_LABEL,
        release_date=None,
        precision=DatePrecision.UNKNOWN,
        source=None,
        suggested_date=None,
    )


def upcoming_for(db: Session, user_id: uuid.UUID, today: date) -> list[UpcomingRelease]:
    follows = db.scalars(
        select(Follow)
        .join(Follow.work)
        .options(contains_eager(Follow.work))
        .where(Follow.user_id == user_id)
    ).all()
    next_by_work = _next_releases(db, [follow.work_id for follow in follows], today)

    items = [_upcoming_item(follow, next_by_work.get(follow.work_id), today) for follow in follows]
    return sorted(
        items,
        key=lambda item: (item.release_date is None, item.release_date or date.max, item.work.title.lower()),
    )

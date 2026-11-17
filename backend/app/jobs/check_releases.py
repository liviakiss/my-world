import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.catalogue.base import CatalogueError, ReleaseChecker, ReleaseInfo
from app.catalogue.registry import get_release_checkers
from app.database import SessionLocal
from app.models import DataSource, Follow, Release, Work
from app.services.analytics import track_event

logger = logging.getLogger(__name__)

CHECK_INTERVAL = timedelta(hours=20)
BATCH_SIZE = 200


@dataclass
class JobResult:
    checked: int = 0
    found: int = 0
    failed: int = 0


def due_works(
    db: Session, sources: list[DataSource], now: datetime, batch_size: int = BATCH_SIZE
) -> list[Work]:
    query = (
        select(Work)
        .where(
            Work.id.in_(select(Follow.work_id)),
            Work.source.in_(sources),
            Work.is_ongoing.is_not(False),
            or_(Work.last_checked_at.is_(None), Work.last_checked_at < now - CHECK_INTERVAL),
        )
        .order_by(Work.last_checked_at.asc().nulls_first(), Work.id)
        .limit(batch_size)
    )
    return list(db.scalars(query).all())


def apply_release_info(db: Session, work: Work, info: ReleaseInfo | None) -> bool:
    if info is None:
        return False
    if info.is_ongoing is not None:
        work.is_ongoing = info.is_ongoing
    if info.total_units is not None:
        work.total_units = info.total_units
    if info.next_label is None:
        return False

    existing = db.scalar(
        select(Release).where(Release.work_id == work.id, Release.label == info.next_label)
    )
    if existing is not None:
        existing.release_date = info.next_date
        existing.precision = info.next_precision
        return False

    db.add(
        Release(
            work_id=work.id,
            label=info.next_label,
            release_date=info.next_date,
            precision=info.next_precision,
            source=work.source,
        )
    )
    follower_ids = db.scalars(select(Follow.user_id).where(Follow.work_id == work.id)).all()
    for user_id in follower_ids:
        track_event(db, user_id, "release_found", media_type=work.media_type.value)
    return True


def check_releases(
    db: Session,
    checkers: dict[DataSource, ReleaseChecker],
    now: datetime | None = None,
    batch_size: int = BATCH_SIZE,
) -> JobResult:
    now = now or datetime.now(timezone.utc)
    result = JobResult()

    for work in due_works(db, list(checkers), now, batch_size):
        work.last_checked_at = now
        try:
            info = checkers[work.source].release_info(work.external_id)
        except CatalogueError as exc:
            logger.warning("Release check failed for work %s: %s", work.id, exc)
            result.failed += 1
            db.commit()
            continue

        if apply_release_info(db, work, info):
            result.found += 1
        result.checked += 1
        db.commit()

    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        result = check_releases(db, get_release_checkers())
    logger.info("Release check finished: %s", result)


if __name__ == "__main__":
    main()

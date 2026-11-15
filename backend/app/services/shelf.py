import uuid
from datetime import date, datetime, timezone

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.models import Entry, EntryStatus, Work


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Work.created_by_user_id.is_(None), Work.created_by_user_id == user_id)


def get_visible_work(db: Session, work_id: uuid.UUID, user_id: uuid.UUID) -> Work | None:
    return db.scalar(select(Work).where(Work.id == work_id, visible_to(user_id)))


def get_own_entry(db: Session, entry_id: uuid.UUID, user_id: uuid.UUID) -> Entry | None:
    return db.scalar(select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id))


def count_custom_works(db: Session, user_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Work).where(Work.created_by_user_id == user_id)
    )


def apply_status_side_effects(entry: Entry, work: Work) -> None:
    if entry.status == EntryStatus.IN_PROGRESS and entry.started_on is None:
        entry.started_on = today_utc()

    if entry.status == EntryStatus.FINISHED:
        if entry.finished_on is None:
            entry.finished_on = today_utc()
        if work.total_units is not None:
            entry.progress = work.total_units

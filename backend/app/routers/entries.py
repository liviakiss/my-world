import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Entry, EntryStatus, MediaType, User, Work
from app.schemas.entries import EntryCreate, EntryResponse, EntryUpdate
from app.security.rate_limit import write_limiter
from app.services.analytics import track_event
from app.services.shelf import apply_status_side_effects, get_own_entry, get_visible_work

router = APIRouter(prefix="/entries", tags=["shelf"])


def _entry_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found.")


def _invalid(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"field": field, "message": message}],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EntryResponse,
    dependencies=[Depends(write_limiter)],
)
def add_entry(
    payload: EntryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Entry:
    work = get_visible_work(db, payload.work_id, user.id)
    if work is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work not found.")

    entry = Entry(user_id=user.id, work=work, status=payload.status)
    apply_status_side_effects(entry, work)
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This work is already on your shelf."
        ) from None

    media_type = work.media_type.value
    track_event(db, user.id, "item_added", media_type=media_type, status=entry.status.value)
    if entry.status == EntryStatus.FINISHED:
        track_event(db, user.id, "item_finished", media_type=media_type)
    db.commit()
    return entry


@router.get("", response_model=list[EntryResponse])
def list_entries(
    entry_status: EntryStatus | None = Query(default=None, alias="status"),
    media_type: MediaType | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Entry]:
    query = (
        select(Entry)
        .join(Entry.work)
        .options(contains_eager(Entry.work))
        .where(Entry.user_id == user.id)
    )
    if entry_status is not None:
        query = query.where(Entry.status == entry_status)
    if media_type is not None:
        query = query.where(Work.media_type == media_type)

    query = query.order_by(Entry.updated_at.desc(), Entry.id).limit(limit).offset(offset)
    return list(db.scalars(query).all())


@router.get("/{entry_id}", response_model=EntryResponse)
def get_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Entry:
    entry = get_own_entry(db, entry_id, user.id)
    if entry is None:
        raise _entry_not_found()
    return entry


@router.patch("/{entry_id}", response_model=EntryResponse, dependencies=[Depends(write_limiter)])
def update_entry(
    entry_id: uuid.UUID,
    payload: EntryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Entry:
    entry = get_own_entry(db, entry_id, user.id)
    if entry is None:
        raise _entry_not_found()

    work = entry.work
    old_status, old_rating = entry.status, entry.rating
    changes = payload.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(entry, field, value)
    apply_status_side_effects(entry, work)

    if entry.started_on and entry.finished_on and entry.finished_on < entry.started_on:
        raise _invalid("finished_on", "finished_on cannot be before started_on")
    if work.total_units is not None and entry.progress > work.total_units:
        raise _invalid("progress", f"progress cannot be more than {work.total_units}")

    media_type = work.media_type.value
    if entry.status != old_status:
        track_event(
            db,
            user.id,
            "status_changed",
            media_type=media_type,
            from_status=old_status.value,
            to_status=entry.status.value,
        )
        if entry.status == EntryStatus.FINISHED:
            track_event(db, user.id, "item_finished", media_type=media_type)
    if entry.rating is not None and entry.rating != old_rating:
        track_event(db, user.id, "rating_set", media_type=media_type, rating=float(entry.rating))

    db.commit()
    return entry


@router.delete(
    "/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(write_limiter)]
)
def delete_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    entry = get_own_entry(db, entry_id, user.id)
    if entry is None:
        raise _entry_not_found()
    db.delete(entry)
    db.commit()

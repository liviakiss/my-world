import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Follow, User
from app.schemas.follows import FollowCreate, FollowResponse, FollowUpdate, UpcomingRelease
from app.security.rate_limit import write_limiter
from app.services.analytics import track_event
from app.services.follows import MAX_FOLLOWS_PER_USER, count_follows, get_own_follow, upcoming_for
from app.services.shelf import get_visible_work, today_utc

router = APIRouter(tags=["releases"])


def _follow_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow not found.")


@router.post(
    "/follows",
    status_code=status.HTTP_201_CREATED,
    response_model=FollowResponse,
    dependencies=[Depends(write_limiter)],
)
def follow_work(
    payload: FollowCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Follow:
    work = get_visible_work(db, payload.work_id, user.id)
    if work is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work not found.")
    if count_follows(db, user.id) >= MAX_FOLLOWS_PER_USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Follow limit reached.")

    follow = Follow(user_id=user.id, work=work, **payload.model_dump(exclude={"work_id"}))
    db.add(follow)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You already follow this."
        ) from None

    track_event(db, user.id, "series_followed", media_type=work.media_type.value, automatic=False)
    db.commit()
    return follow


@router.get("/follows", response_model=list[FollowResponse])
def list_follows(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Follow]:
    query = (
        select(Follow)
        .join(Follow.work)
        .options(contains_eager(Follow.work))
        .where(Follow.user_id == user.id)
        .order_by(Follow.created_at.desc(), Follow.id)
    )
    return list(db.scalars(query).all())


@router.patch(
    "/follows/{follow_id}", response_model=FollowResponse, dependencies=[Depends(write_limiter)]
)
def update_follow(
    follow_id: uuid.UUID,
    payload: FollowUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Follow:
    follow = get_own_follow(db, follow_id, user.id)
    if follow is None:
        raise _follow_not_found()
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(follow, field, value)
    db.commit()
    return follow


@router.delete(
    "/follows/{follow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_limiter)],
)
def unfollow(
    follow_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    follow = get_own_follow(db, follow_id, user.id)
    if follow is None:
        raise _follow_not_found()
    db.delete(follow)
    db.commit()


@router.get("/releases/upcoming", response_model=list[UpcomingRelease])
def upcoming_releases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UpcomingRelease]:
    return upcoming_for(db, user.id, today_utc())

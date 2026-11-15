import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import DataSource, User, Work
from app.schemas.works import CustomWorkCreate, WorkResponse
from app.security.rate_limit import write_limiter
from app.services.shelf import count_custom_works, get_visible_work

router = APIRouter(prefix="/works", tags=["works"])

MAX_CUSTOM_WORKS_PER_USER = 1000


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkResponse,
    dependencies=[Depends(write_limiter)],
)
def create_custom_work(
    payload: CustomWorkCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Work:
    if count_custom_works(db, user.id) >= MAX_CUSTOM_WORKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Custom work limit reached."
        )

    work = Work(**payload.model_dump(), source=DataSource.CUSTOM, created_by_user_id=user.id)
    db.add(work)
    db.commit()
    return work


@router.get("/{work_id}", response_model=WorkResponse)
def get_work(
    work_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Work:
    work = get_visible_work(db, work_id, user.id)
    if work is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work not found.")
    return work

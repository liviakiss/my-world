from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.stats import PersonalStats
from app.services.stats import personal_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/me", response_model=PersonalStats)
def my_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalStats:
    return personal_stats(db, user.id)

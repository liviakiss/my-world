from datetime import datetime

from pydantic import BaseModel

from app.models import MediaType


class StatusTotals(BaseModel):
    entries: int
    want: int
    in_progress: int
    finished: int
    paused: int
    dropped: int


class MediaTypeTotal(BaseModel):
    media_type: MediaType
    total: int
    finished: int


class MonthCount(BaseModel):
    month: str
    count: int


class RatingBucket(BaseModel):
    rating: float
    count: int


class Backlog(BaseModel):
    count: int
    oldest_added_at: datetime | None
    average_age_days: float | None


class PersonalStats(BaseModel):
    totals: StatusTotals
    completion_rate: float | None
    by_media_type: list[MediaTypeTotal]
    finished_per_month: list[MonthCount]
    average_days_to_finish: float | None
    average_rating: float | None
    rating_distribution: list[RatingBucket]
    backlog: Backlog

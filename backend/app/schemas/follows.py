import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import DatePrecision
from app.models.follow import MANUAL_LABEL_MAX_LENGTH
from app.schemas.works import WorkSummary

class FollowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    work_id: uuid.UUID
    manual_release_date: date | None = None
    manual_release_label: str | None = Field(default=None, max_length=MANUAL_LABEL_MAX_LENGTH)
    manual_release_precision: DatePrecision = DatePrecision.DAY


class FollowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    manual_release_date: date | None = None
    manual_release_label: str | None = Field(default=None, max_length=MANUAL_LABEL_MAX_LENGTH)
    manual_release_precision: DatePrecision | None = None

    @model_validator(mode="after")
    def reject_null_precision(self) -> "FollowUpdate":
        if "manual_release_precision" in self.model_fields_set and self.manual_release_precision is None:
            raise ValueError("manual_release_precision cannot be null")
        return self


class FollowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work: WorkSummary
    manual_release_date: date | None
    manual_release_label: str | None
    manual_release_precision: DatePrecision
    created_at: datetime


class UpcomingRelease(BaseModel):
    follow_id: uuid.UUID
    work: WorkSummary
    label: str
    release_date: date | None
    precision: DatePrecision
    source: str | None
    suggested_date: date | None

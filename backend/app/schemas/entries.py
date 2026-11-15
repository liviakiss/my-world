import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import EntryStatus
from app.models.entry import NOTES_MAX_LENGTH
from app.schemas.works import WorkSummary

Rating = Annotated[
    Decimal, Field(ge=Decimal("0.5"), le=Decimal("5"), multiple_of=Decimal("0.5"))
]
NON_NULLABLE_FIELDS = ("status", "progress")


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_id: uuid.UUID
    status: EntryStatus = EntryStatus.WANT


class EntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: EntryStatus | None = None
    progress: int | None = Field(default=None, ge=0, le=100_000)
    rating: Rating | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)
    started_on: date | None = None
    finished_on: date | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "EntryUpdate":
        for field in NON_NULLABLE_FIELDS:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class EntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: EntryStatus
    progress: int
    rating: float | None
    notes: str | None
    started_on: date | None
    finished_on: date | None
    created_at: datetime
    updated_at: datetime
    work: WorkSummary

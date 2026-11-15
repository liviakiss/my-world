import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import DataSource, MediaType

TITLE_MAX_LENGTH = 500
DESCRIPTION_MAX_LENGTH = 5000
MAX_LIST_ITEMS = 10
LIST_ITEM_MAX_LENGTH = 200

ShortText = Annotated[str, Field(min_length=1, max_length=LIST_ITEM_MAX_LENGTH)]


class CustomWorkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    media_type: MediaType
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    creators: list[ShortText] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    genres: list[ShortText] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    total_units: int | None = Field(default=None, ge=1, le=100_000)


class WorkSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    media_type: MediaType
    title: str
    cover_url: str | None
    total_units: int | None
    source: DataSource


class WorkResponse(WorkSummary):
    description: str | None
    creators: list[str]
    genres: list[str]

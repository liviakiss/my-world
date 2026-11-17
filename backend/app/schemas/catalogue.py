from pydantic import BaseModel, ConfigDict, Field

from app.catalogue.base import CatalogueItem
from app.models import DataSource, MediaType


class CatalogueResult(BaseModel):
    source: DataSource
    external_id: str
    media_type: MediaType
    title: str
    creators: list[str]
    cover_url: str | None
    total_units: int | None
    release_year: int | None

    @classmethod
    def from_item(cls, item: CatalogueItem) -> "CatalogueResult":
        return cls(
            source=item.source,
            external_id=item.external_id,
            media_type=item.media_type,
            title=item.title,
            creators=item.creators,
            cover_url=item.cover_url,
            total_units=item.total_units,
            release_year=item.release_date.year if item.release_date else None,
        )


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_type: MediaType
    external_id: str = Field(min_length=1, max_length=100)

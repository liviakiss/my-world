from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.models import DataSource, DatePrecision, MediaType


class CatalogueError(Exception):
    pass


@dataclass(frozen=True)
class CatalogueItem:
    source: DataSource
    external_id: str
    media_type: MediaType
    title: str
    description: str | None = None
    creators: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    cover_url: str | None = None
    total_units: int | None = None
    release_date: date | None = None
    release_date_precision: DatePrecision = DatePrecision.UNKNOWN


class CatalogueAdapter(Protocol):
    source: DataSource

    def search(self, query: str, media_type: MediaType) -> list[CatalogueItem]: ...

    def fetch(self, external_id: str, media_type: MediaType) -> CatalogueItem | None: ...

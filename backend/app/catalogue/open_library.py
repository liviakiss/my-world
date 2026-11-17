import re
from datetime import date
from typing import Any

import httpx2

from app.catalogue.base import CatalogueItem
from app.catalogue.http import get_json
from app.catalogue.sanitize import (
    clean_line,
    clean_list,
    clean_text,
    parse_year,
    positive_int,
    safe_https_url,
)
from app.models import DataSource, DatePrecision, MediaType

BASE_URL = "https://openlibrary.org"
COVER_HOSTS = {"covers.openlibrary.org"}
WORK_ID = re.compile(r"OL\d{1,10}W")
AUTHOR_KEY = re.compile(r"/authors/OL\d{1,10}A")
SEARCH_FIELDS = "key,title,author_name,first_publish_year,cover_i,number_of_pages_median,subject"
SEARCH_LIMIT = 20
MAX_AUTHORS = 3


def _cover_url(cover_id: object) -> str | None:
    cover = positive_int(cover_id, maximum=10**10)
    if cover is None:
        return None
    return safe_https_url(f"https://covers.openlibrary.org/b/id/{cover}-L.jpg", COVER_HOSTS)


def _release(year: int | None) -> dict[str, Any]:
    if year is None:
        return {}
    return {"release_date": date(year, 1, 1), "release_date_precision": DatePrecision.YEAR}


class OpenLibraryAdapter:
    source = DataSource.OPEN_LIBRARY

    def __init__(self, client: httpx2.Client) -> None:
        self.client = client

    def search(self, query: str, media_type: MediaType) -> list[CatalogueItem]:
        data = get_json(
            self.client,
            f"{BASE_URL}/search.json",
            params={"q": query, "fields": SEARCH_FIELDS, "limit": SEARCH_LIMIT},
        )
        docs = (data or {}).get("docs")
        if not isinstance(docs, list):
            return []
        items = (self._from_search_doc(doc, media_type) for doc in docs if isinstance(doc, dict))
        return [item for item in items if item is not None]

    def fetch(self, external_id: str, media_type: MediaType) -> CatalogueItem | None:
        if not WORK_ID.fullmatch(external_id):
            return None
        work = get_json(self.client, f"{BASE_URL}/works/{external_id}.json")
        if work is None:
            return None
        title = clean_line(work.get("title"), 500)
        if title is None:
            return None

        covers = work.get("covers")
        description = work.get("description")
        if isinstance(description, dict):
            description = description.get("value")

        return CatalogueItem(
            source=self.source,
            external_id=external_id,
            media_type=media_type,
            title=title,
            description=clean_text(description, 5000),
            creators=self._author_names(work.get("authors")),
            genres=clean_list(work.get("subjects"), max_items=5),
            cover_url=_cover_url(covers[0]) if isinstance(covers, list) and covers else None,
            **_release(parse_year(work.get("first_publish_date"))),
        )

    def _from_search_doc(self, doc: dict[str, Any], media_type: MediaType) -> CatalogueItem | None:
        key = doc.get("key")
        external_id = key.removeprefix("/works/") if isinstance(key, str) else ""
        title = clean_line(doc.get("title"), 500)
        if not WORK_ID.fullmatch(external_id) or title is None:
            return None

        return CatalogueItem(
            source=self.source,
            external_id=external_id,
            media_type=media_type,
            title=title,
            creators=clean_list(doc.get("author_name")),
            genres=clean_list(doc.get("subject"), max_items=5),
            cover_url=_cover_url(doc.get("cover_i")),
            total_units=positive_int(doc.get("number_of_pages_median")),
            **_release(parse_year(doc.get("first_publish_year"))),
        )

    def _author_names(self, authors: object) -> list[str]:
        if not isinstance(authors, list):
            return []
        keys = [
            entry["author"]["key"]
            for entry in authors
            if isinstance(entry, dict)
            and isinstance(entry.get("author"), dict)
            and isinstance(entry["author"].get("key"), str)
            and AUTHOR_KEY.fullmatch(entry["author"]["key"])
        ][:MAX_AUTHORS]

        names = []
        for key in keys:
            author = get_json(self.client, f"{BASE_URL}{key}.json") or {}
            name = clean_line(author.get("name"), 200)
            if name:
                names.append(name)
        return names

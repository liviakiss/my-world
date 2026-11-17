import re
from dataclasses import replace
from typing import Any

import httpx2

from app.catalogue.base import CatalogueItem, ReleaseInfo
from app.catalogue.http import get_json
from app.catalogue.sanitize import (
    clean_line,
    clean_list,
    clean_text,
    parse_iso_date,
    positive_int,
    safe_https_url,
)
from app.models import DataSource, DatePrecision, MediaType

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
IMAGE_HOSTS = {"image.tmdb.org"}
EXTERNAL_ID = re.compile(r"(movie|tv):(\d{1,10})")
POSTER_PATH = re.compile(r"/[A-Za-z0-9_-]{1,100}\.(jpg|png)")
SEARCH_LIMIT = 20
ONGOING_STATUSES = {"Returning Series", "In Production", "Planned", "Pilot"}
ENDED_STATUSES = {"Ended", "Canceled"}


def tmdb_kind(media_type: MediaType) -> str:
    return "movie" if media_type == MediaType.MOVIE else "tv"


def _poster_url(path: object) -> str | None:
    if not isinstance(path, str) or not POSTER_PATH.fullmatch(path):
        return None
    return safe_https_url(f"{IMAGE_BASE_URL}{path}", IMAGE_HOSTS)


def _is_ongoing(status: object) -> bool | None:
    if status in ONGOING_STATUSES:
        return True
    if status in ENDED_STATUSES:
        return False
    return None


def _names(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return clean_list([value.get("name") for value in values if isinstance(value, dict)])


class TmdbAdapter:
    source = DataSource.TMDB

    def __init__(self, client: httpx2.Client, api_token: str) -> None:
        self.client = client
        self._auth = {"Authorization": f"Bearer {api_token}"}

    def search(self, query: str, media_type: MediaType) -> list[CatalogueItem]:
        kind = tmdb_kind(media_type)
        data = self._get(f"/search/{kind}", {"query": query, "include_adult": "false"})
        results = (data or {}).get("results")
        if not isinstance(results, list):
            return []
        items = (
            self._parse(kind, result, media_type)
            for result in results[:SEARCH_LIMIT]
            if isinstance(result, dict)
        )
        return [item for item in items if item is not None]

    def fetch(self, external_id: str, media_type: MediaType) -> CatalogueItem | None:
        match = EXTERNAL_ID.fullmatch(external_id)
        if match is None or match.group(1) != tmdb_kind(media_type):
            return None
        kind, tmdb_id = match.groups()
        data = self._get(f"/{kind}/{tmdb_id}")
        return self._parse(kind, data, media_type) if data else None

    def release_info(self, external_id: str) -> ReleaseInfo | None:
        match = EXTERNAL_ID.fullmatch(external_id)
        if match is None or match.group(1) != "tv":
            return None
        data = self._get(f"/tv/{match.group(2)}")
        if data is None:
            return None

        info = ReleaseInfo(
            is_ongoing=_is_ongoing(data.get("status")),
            total_units=positive_int(data.get("number_of_episodes")),
        )
        upcoming = data.get("next_episode_to_air")
        if not isinstance(upcoming, dict):
            return info

        season = positive_int(upcoming.get("season_number"), maximum=1000)
        episode = positive_int(upcoming.get("episode_number"), maximum=10_000)
        air_date = parse_iso_date(upcoming.get("air_date"))
        if season is None or episode is None:
            return info
        return replace(
            info,
            next_label=f"Season {season}, episode {episode}",
            next_date=air_date,
            next_precision=DatePrecision.DAY if air_date else DatePrecision.UNKNOWN,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return get_json(self.client, f"{BASE_URL}{path}", params=params, headers=self._auth)

    def _parse(self, kind: str, data: dict[str, Any], media_type: MediaType) -> CatalogueItem | None:
        tmdb_id = positive_int(data.get("id"), maximum=10**10)
        is_movie = kind == "movie"
        title = clean_line(data.get("title" if is_movie else "name"), 500)
        if tmdb_id is None or title is None:
            return None

        released = parse_iso_date(data.get("release_date" if is_movie else "first_air_date"))
        return CatalogueItem(
            source=self.source,
            external_id=f"{kind}:{tmdb_id}",
            media_type=media_type,
            title=title,
            description=clean_text(data.get("overview"), 5000),
            creators=[] if is_movie else _names(data.get("created_by")),
            genres=_names(data.get("genres")),
            cover_url=_poster_url(data.get("poster_path")),
            total_units=1 if is_movie else positive_int(data.get("number_of_episodes")),
            release_date=released,
            release_date_precision=DatePrecision.DAY if released else DatePrecision.UNKNOWN,
            is_ongoing=None if is_movie else _is_ongoing(data.get("status")),
        )

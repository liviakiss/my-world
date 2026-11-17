from collections.abc import Callable

import httpx2
import pytest

from app.catalogue.base import CatalogueError
from app.catalogue.open_library import OpenLibraryAdapter
from app.catalogue.tmdb import TmdbAdapter
from app.models import DatePrecision, MediaType

Handler = Callable[[httpx2.Request], httpx2.Response]


def client_for(routes: dict[str, object], seen: list[httpx2.Request] | None = None) -> httpx2.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        result = routes.get(request.url.path)
        if result is None:
            return httpx2.Response(404)
        if isinstance(result, int):
            return httpx2.Response(result)
        return httpx2.Response(200, json=result)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


OL_SEARCH = {
    "docs": [
        {
            "key": "/works/OL27448W",
            "title": "The Lord of the Rings",
            "author_name": ["J.R.R. Tolkien", "J.R.R. Tolkien"],
            "first_publish_year": 1954,
            "cover_i": 14625765,
            "number_of_pages_median": 1193,
            "subject": ["Fantasy", "Fiction", "Elves", "Hobbits", "Middle Earth", "Rings"],
        },
        {"key": "/authors/OL1A", "title": "Not a work"},
        {"key": "/works/OL1W"},
    ]
}

OL_WORK = {
    "title": "The Hobbit",
    "description": {"type": "/type/text", "value": "<b>In a hole</b> in the ground\n\n\n\nlived a hobbit."},
    "covers": [6979861],
    "subjects": ["Fantasy"],
    "first_publish_date": "September 21, 1937",
    "authors": [
        {"author": {"key": "/authors/OL26320A"}},
        {"author": {"key": "https://evil.example/steal"}},
    ],
}


def test_open_library_search_parses_and_skips_bad_docs():
    adapter = OpenLibraryAdapter(client_for({"/search.json": OL_SEARCH}))

    items = adapter.search("lord of the rings", MediaType.BOOK)

    assert len(items) == 1
    book = items[0]
    assert book.external_id == "OL27448W"
    assert book.creators == ["J.R.R. Tolkien"]
    assert len(book.genres) == 5
    assert book.cover_url == "https://covers.openlibrary.org/b/id/14625765-L.jpg"
    assert book.total_units == 1193
    assert book.release_date.year == 1954
    assert book.release_date_precision == DatePrecision.YEAR


def test_open_library_fetch_cleans_text_and_only_follows_valid_author_keys():
    seen: list[httpx2.Request] = []
    routes = {
        "/works/OL262758W.json": OL_WORK,
        "/authors/OL26320A.json": {"name": "J.R.R. Tolkien"},
    }
    adapter = OpenLibraryAdapter(client_for(routes, seen))

    book = adapter.fetch("OL262758W", MediaType.BOOK)

    assert book.description == "In a hole in the ground\n\nlived a hobbit."
    assert book.creators == ["J.R.R. Tolkien"]
    assert book.release_date.year == 1937
    assert all(request.url.host == "openlibrary.org" for request in seen)


def test_open_library_rejects_malformed_ids_without_any_request():
    seen: list[httpx2.Request] = []
    adapter = OpenLibraryAdapter(client_for({}, seen))

    for bad_id in ["../../admin", "OL1W/../x", "OL1W?x=1", "https://evil.example"]:
        assert adapter.fetch(bad_id, MediaType.BOOK) is None
    assert seen == []


def test_upstream_errors_become_catalogue_errors():
    adapter = OpenLibraryAdapter(client_for({"/search.json": 500}))

    with pytest.raises(CatalogueError):
        adapter.search("anything", MediaType.BOOK)


def test_oversized_titles_are_truncated():
    doc = {"key": "/works/OL5W", "title": "A" * 2000}
    adapter = OpenLibraryAdapter(client_for({"/search.json": {"docs": [doc]}}))

    item = adapter.search("a", MediaType.BOOK)[0]

    assert len(item.title) == 500


TMDB_TV = {
    "id": 1396,
    "name": "Frieren: Beyond Journey's End",
    "overview": "An elf mage outlives her party.",
    "first_air_date": "2023-09-29",
    "number_of_episodes": 28,
    "poster_path": "/frieren.jpg",
    "genres": [{"name": "Animation"}, {"name": "Fantasy"}],
    "created_by": [{"name": "Kanehito Yamada"}],
}


def test_tmdb_fetch_tv_sends_token_in_header_not_url():
    seen: list[httpx2.Request] = []
    adapter = TmdbAdapter(client_for({"/3/tv/1396": TMDB_TV}, seen), api_token="secret-token")

    show = adapter.fetch("tv:1396", MediaType.ANIME)

    assert show.title == "Frieren: Beyond Journey's End"
    assert show.total_units == 28
    assert show.genres == ["Animation", "Fantasy"]
    assert show.cover_url == "https://image.tmdb.org/t/p/w500/frieren.jpg"
    assert show.release_date_precision == DatePrecision.DAY
    assert seen[0].headers["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in str(seen[0].url)


def test_tmdb_rejects_unsafe_poster_paths_and_mismatched_ids():
    poisoned = {**TMDB_TV, "poster_path": "//evil.example/x.jpg"}
    adapter = TmdbAdapter(client_for({"/3/tv/1396": poisoned}), api_token="t")

    assert adapter.fetch("tv:1396", MediaType.TV).cover_url is None
    assert adapter.fetch("movie:1396", MediaType.TV) is None
    assert adapter.fetch("tv:1396/../../account", MediaType.TV) is None


def test_tmdb_search_movies():
    results = {"results": [{"id": 550, "title": "Fight Club", "release_date": "1999-10-15"}]}
    adapter = TmdbAdapter(client_for({"/3/search/movie": results}), api_token="t")

    movies = adapter.search("fight club", MediaType.MOVIE)

    assert movies[0].external_id == "movie:550"
    assert movies[0].total_units == 1

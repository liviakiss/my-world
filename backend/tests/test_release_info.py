from datetime import date

import httpx2

from app.catalogue.tmdb import TmdbAdapter
from app.models import DatePrecision


def adapter_returning(payload: dict | None) -> TmdbAdapter:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if payload is None:
            return httpx2.Response(404)
        return httpx2.Response(200, json=payload)

    return TmdbAdapter(httpx2.Client(transport=httpx2.MockTransport(handler)), api_token="t")


def test_next_episode_is_read_from_tmdb():
    adapter = adapter_returning(
        {
            "status": "Returning Series",
            "number_of_episodes": 28,
            "next_episode_to_air": {"air_date": "2027-01-10", "season_number": 2, "episode_number": 1},
        }
    )

    info = adapter.release_info("tv:1")

    assert info.is_ongoing is True
    assert info.total_units == 28
    assert info.next_label == "Season 2, episode 1"
    assert info.next_date == date(2027, 1, 10)
    assert info.next_precision == DatePrecision.DAY


def test_ended_show_has_no_next_release():
    info = adapter_returning({"status": "Ended", "number_of_episodes": 62}).release_info("tv:1")

    assert info.is_ongoing is False
    assert info.next_label is None


def test_announced_episode_without_date_keeps_unknown_precision():
    adapter = adapter_returning(
        {"status": "Returning Series", "next_episode_to_air": {"season_number": 3, "episode_number": 1}}
    )

    info = adapter.release_info("tv:1")

    assert info.next_label == "Season 3, episode 1"
    assert info.next_date is None
    assert info.next_precision == DatePrecision.UNKNOWN


def test_movies_and_bad_ids_are_not_checked():
    adapter = adapter_returning({"status": "Returning Series"})

    assert adapter.release_info("movie:550") is None
    assert adapter.release_info("tv:1/../../account") is None


def test_garbage_episode_numbers_are_ignored():
    adapter = adapter_returning(
        {"status": "Returning Series", "next_episode_to_air": {"season_number": "x", "episode_number": -5}}
    )

    assert adapter.release_info("tv:1").next_label is None

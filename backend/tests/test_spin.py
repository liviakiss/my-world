from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AnalyticsEvent, EntryStatus, MediaType
from tests.helpers import add_catalogue_work, add_entry, current_user_id, logged_in_client


def spin(client, **options):
    return client.post("/entries/spin", json=options)


def test_spin_requires_login():
    assert TestClient(app).post("/entries/spin", json={}).status_code == 401


def test_spin_only_picks_from_the_want_list(db):
    client = logged_in_client("livia@example.com")
    user_id = current_user_id(client)
    wanted = add_catalogue_work(db, title="Wanted")
    add_entry(db, user_id, wanted, EntryStatus.WANT)
    add_entry(db, user_id, add_catalogue_work(db, title="Done"), EntryStatus.FINISHED)
    add_entry(db, user_id, add_catalogue_work(db, title="Reading"), EntryStatus.IN_PROGRESS)

    titles = {spin(client).json()["work"]["title"] for _ in range(10)}

    assert titles == {"Wanted"}


def test_spin_can_filter_by_media_type_and_include_paused(db):
    client = logged_in_client("livia@example.com")
    user_id = current_user_id(client)
    add_entry(db, user_id, add_catalogue_work(db, title="A Book"), EntryStatus.WANT)
    show = add_catalogue_work(db, title="A Paused Show", media_type=MediaType.TV)
    add_entry(db, user_id, show, EntryStatus.PAUSED)

    only_tv = spin(client, media_type="tv")
    tv_with_paused = spin(client, media_type="tv", include_paused=True)

    assert only_tv.status_code == 404
    assert tv_with_paused.json()["work"]["title"] == "A Paused Show"


def test_spin_never_picks_another_users_entry(db):
    me = logged_in_client("me@example.com")
    other = logged_in_client("other@example.com")
    add_entry(db, current_user_id(other), add_catalogue_work(db), EntryStatus.WANT)

    assert spin(me).status_code == 404


def test_spin_is_tracked_without_titles(db):
    client = logged_in_client("livia@example.com")
    add_entry(db, current_user_id(client), add_catalogue_work(db, title="Secret"), EntryStatus.WANT)

    spin(client)

    event = db.scalar(select(AnalyticsEvent).where(AnalyticsEvent.event_type == "spin_wheel_used"))
    assert event.properties == {"media_type": "any"}


def test_unknown_spin_options_are_rejected():
    client = logged_in_client("livia@example.com")

    assert spin(client, user_id="someone-else").status_code == 422

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import DataSource, DatePrecision, EntryStatus, Follow, MediaType, Release, Work
from tests.helpers import add_catalogue_work, add_entry, current_user_id, logged_in_client


def today() -> date:
    return datetime.now(timezone.utc).date()


def ongoing_show(db, title: str = "Ongoing Show") -> Work:
    work = add_catalogue_work(db, title=title, media_type=MediaType.TV, total_units=12)
    work.is_ongoing = True
    db.commit()
    return work


def add_release(db, work: Work, label: str, on: date) -> None:
    db.add(
        Release(
            work_id=work.id,
            label=label,
            release_date=on,
            precision=DatePrecision.DAY,
            source=DataSource.TMDB,
        )
    )
    db.commit()


def follow(client, work_id, **fields):
    return client.post("/follows", json={"work_id": str(work_id), **fields})


def upcoming(client) -> list[dict]:
    return client.get("/releases/upcoming").json()


def test_following_requires_login(db):
    work = add_catalogue_work(db)

    assert follow(TestClient(app), work.id).status_code == 401


def test_follow_once_only(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")

    first = follow(client, work.id)
    second = follow(client, work.id)

    assert first.status_code == 201
    assert second.status_code == 409


def test_cannot_follow_someone_elses_custom_work():
    owner = logged_in_client("owner@example.com")
    other = logged_in_client("other@example.com")
    work_id = owner.post("/works", json={"media_type": "book", "title": "Private"}).json()["id"]

    assert follow(other, work_id).status_code == 404


def test_invalid_follow_input_is_rejected(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")

    too_long = follow(client, work.id, manual_release_label="x" * 201)
    smuggled = follow(client, work.id, user_id="00000000-0000-0000-0000-000000000000")

    assert too_long.status_code == smuggled.status_code == 422


def test_other_users_cannot_change_or_remove_my_follow(db):
    work = add_catalogue_work(db)
    owner = logged_in_client("owner@example.com")
    attacker = logged_in_client("attacker@example.com")
    follow_id = follow(owner, work.id).json()["id"]

    change = attacker.patch(f"/follows/{follow_id}", json={"manual_release_label": "hacked"})
    remove = attacker.delete(f"/follows/{follow_id}")

    assert change.status_code == remove.status_code == 404
    assert owner.get("/follows").json()[0]["manual_release_label"] is None


def test_my_own_date_wins_and_the_system_date_is_suggested(db):
    show = ongoing_show(db)
    add_release(db, show, "Season 2, episode 1", today() + timedelta(days=30))
    client = logged_in_client("livia@example.com")
    follow(client, show.id, manual_release_date=str(today() + timedelta(days=10)), manual_release_label="I heard")

    item = upcoming(client)[0]

    assert item["source"] == "you"
    assert item["label"] == "I heard"
    assert item["release_date"] == str(today() + timedelta(days=10))
    assert item["suggested_date"] == str(today() + timedelta(days=30))


def test_clearing_my_date_accepts_the_system_date(db):
    show = ongoing_show(db)
    add_release(db, show, "Season 2, episode 1", today() + timedelta(days=30))
    client = logged_in_client("livia@example.com")
    follow_id = follow(client, show.id, manual_release_date=str(today() + timedelta(days=10))).json()["id"]

    client.patch(f"/follows/{follow_id}", json={"manual_release_date": None})
    item = upcoming(client)[0]

    assert item["source"] == "tmdb"
    assert item["label"] == "Season 2, episode 1"
    assert item["suggested_date"] is None


def test_upcoming_is_sorted_and_ignores_past_releases(db):
    soon = ongoing_show(db, "Soon")
    later = ongoing_show(db, "Later")
    unknown = ongoing_show(db, "Unknown")
    add_release(db, soon, "S1E5", today() + timedelta(days=3))
    add_release(db, later, "S1E1", today() - timedelta(days=5))
    add_release(db, later, "S1E2", today() + timedelta(days=40))
    client = logged_in_client("livia@example.com")
    for work in (unknown, later, soon):
        follow(client, work.id)

    items = upcoming(client)

    assert [item["work"]["title"] for item in items] == ["Soon", "Later", "Unknown"]
    assert items[1]["label"] == "S1E2"
    assert items[2]["release_date"] is None


def test_adding_an_ongoing_show_follows_it_automatically(db):
    show = ongoing_show(db)
    book = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")

    client.post("/entries", json={"work_id": str(show.id)})
    client.post("/entries", json={"work_id": str(book.id)})

    followed = db.scalars(select(Follow.work_id)).all()
    assert followed == [show.id]


def test_finished_entry_of_an_ongoing_show_is_waiting(db):
    show = ongoing_show(db)
    ended = add_catalogue_work(db, title="Ended", media_type=MediaType.TV)
    client = logged_in_client("livia@example.com")
    user_id = current_user_id(client)
    add_entry(db, user_id, show, EntryStatus.FINISHED, progress=12)
    add_entry(db, user_id, ended, EntryStatus.FINISHED)

    waiting = {e["work"]["title"]: e["waiting"] for e in client.get("/entries").json()}

    assert waiting == {"Ongoing Show": True, "Ended": False}

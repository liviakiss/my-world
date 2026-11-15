from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AnalyticsEvent, Entry, MediaType
from tests.helpers import add_catalogue_work, logged_in_client


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def events(db) -> list[AnalyticsEvent]:
    return list(db.scalars(select(AnalyticsEvent).order_by(AnalyticsEvent.created_at)))


def add_to_shelf(client, work_id, status: str = "want"):
    return client.post("/entries", json={"work_id": str(work_id), "status": status})


def test_adding_a_work_creates_an_entry_and_a_private_event(db):
    work = add_catalogue_work(db, title="Secret Title")
    client = logged_in_client("livia@example.com")

    response = add_to_shelf(client, work.id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "want"
    assert body["work"]["title"] == "Secret Title"
    added = [e for e in events(db) if e.event_type == "item_added"]
    assert added[0].properties == {"media_type": "book", "status": "want"}
    assert "Secret Title" not in str(added[0].properties)


def test_same_work_cannot_be_added_twice(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")

    add_to_shelf(client, work.id)
    second = add_to_shelf(client, work.id)

    assert second.status_code == 409


def test_starting_sets_the_start_date(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")

    response = add_to_shelf(client, work.id, status="in_progress")

    assert response.json()["started_on"] == today()


def test_list_shows_only_my_entries_and_filters(db):
    book = add_catalogue_work(db, title="Book")
    show = add_catalogue_work(db, title="Show", media_type=MediaType.TV)
    me = logged_in_client("me@example.com")
    other = logged_in_client("other@example.com")
    add_to_shelf(me, book.id)
    add_to_shelf(me, show.id, status="in_progress")
    add_to_shelf(other, book.id)

    all_mine = me.get("/entries").json()
    in_progress = me.get("/entries", params={"status": "in_progress"}).json()
    books = me.get("/entries", params={"media_type": "book"}).json()

    assert len(all_mine) == 2
    assert [e["work"]["title"] for e in in_progress] == ["Show"]
    assert [e["work"]["title"] for e in books] == ["Book"]


def test_other_users_cannot_read_change_or_delete_my_entry(db):
    work = add_catalogue_work(db)
    owner = logged_in_client("owner@example.com")
    attacker = logged_in_client("attacker@example.com")
    entry_id = add_to_shelf(owner, work.id).json()["id"]

    read = attacker.get(f"/entries/{entry_id}")
    change = attacker.patch(f"/entries/{entry_id}", json={"rating": 0.5})
    delete = attacker.delete(f"/entries/{entry_id}")

    assert read.status_code == change.status_code == delete.status_code == 404
    still_there = owner.get(f"/entries/{entry_id}").json()
    assert still_there["rating"] is None


def test_cannot_shelve_someone_elses_custom_work():
    owner = logged_in_client("owner@example.com")
    attacker = logged_in_client("attacker@example.com")
    work_id = owner.post("/works", json={"media_type": "game", "title": "Private"}).json()["id"]

    response = add_to_shelf(attacker, work_id)

    assert response.status_code == 404


def test_updating_progress_rating_and_notes(db):
    work = add_catalogue_work(db, total_units=300)
    client = logged_in_client("livia@example.com")
    entry_id = add_to_shelf(client, work.id).json()["id"]

    response = client.patch(
        f"/entries/{entry_id}", json={"progress": 120, "rating": 4.5, "notes": "  loving it  "}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["progress"] == 120
    assert body["rating"] == 4.5
    assert body["notes"] == "loving it"


def test_finishing_fills_dates_progress_and_events(db):
    work = add_catalogue_work(db, total_units=300)
    client = logged_in_client("livia@example.com")
    entry_id = add_to_shelf(client, work.id, status="in_progress").json()["id"]

    body = client.patch(f"/entries/{entry_id}", json={"status": "finished"}).json()

    assert body["finished_on"] == today()
    assert body["progress"] == 300
    types = [e.event_type for e in events(db)]
    assert "status_changed" in types and "item_finished" in types
    changed = next(e for e in events(db) if e.event_type == "status_changed")
    assert changed.properties == {
        "media_type": "book",
        "from_status": "in_progress",
        "to_status": "finished",
    }


def test_rating_can_be_cleared(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")
    entry_id = add_to_shelf(client, work.id).json()["id"]
    client.patch(f"/entries/{entry_id}", json={"rating": 3})

    response = client.patch(f"/entries/{entry_id}", json={"rating": None})

    assert response.json()["rating"] is None


def test_invalid_updates_are_rejected_and_nothing_changes(db):
    work = add_catalogue_work(db, total_units=100)
    client = logged_in_client("livia@example.com")
    entry_id = add_to_shelf(client, work.id).json()["id"]
    url = f"/entries/{entry_id}"

    bad_requests = [
        {"rating": 3.7},
        {"rating": 6},
        {"progress": -1},
        {"progress": 101},
        {"status": None},
        {"notes": "x" * 5001},
        {"started_on": "2026-05-10", "finished_on": "2026-05-01"},
        {"user_id": "00000000-0000-0000-0000-000000000000"},
    ]
    statuses = [client.patch(url, json=body).status_code for body in bad_requests]

    assert statuses == [422] * len(bad_requests)
    entry = db.scalar(select(Entry))
    assert entry.progress == 0
    assert entry.rating is None
    assert entry.started_on is None


def test_deleting_an_entry(db):
    work = add_catalogue_work(db)
    client = logged_in_client("livia@example.com")
    entry_id = add_to_shelf(client, work.id).json()["id"]

    assert client.delete(f"/entries/{entry_id}").status_code == 204
    assert client.get(f"/entries/{entry_id}").status_code == 404


def test_shelf_requires_login():
    assert TestClient(app).get("/entries").status_code == 401

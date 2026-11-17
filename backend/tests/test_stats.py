from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models import EntryStatus, MediaType
from tests.helpers import add_catalogue_work, add_entry, current_user_id, logged_in_client


def today() -> date:
    return datetime.now(timezone.utc).date()


def last_month() -> date:
    return today().replace(day=1) - timedelta(days=1)


def test_stats_require_login():
    assert TestClient(app).get("/stats/me").status_code == 401


def test_empty_shelf_gives_zeroes_not_errors():
    client = logged_in_client("livia@example.com")

    stats = client.get("/stats/me").json()

    assert stats["totals"]["entries"] == 0
    assert stats["completion_rate"] is None
    assert stats["average_days_to_finish"] is None
    assert len(stats["finished_per_month"]) == 12
    assert all(month["count"] == 0 for month in stats["finished_per_month"])
    assert len(stats["rating_distribution"]) == 10
    assert stats["backlog"]["count"] == 0


def test_stats_summarise_the_shelf(db):
    client = logged_in_client("livia@example.com")
    user_id = current_user_id(client)
    books = [add_catalogue_work(db, title=f"Book {i}") for i in range(4)]
    show = add_catalogue_work(db, title="Show", media_type=MediaType.TV)

    add_entry(
        db, user_id, books[0], EntryStatus.FINISHED,
        started_on=today() - timedelta(days=10), finished_on=today(), rating=Decimal("4.5"),
    )
    add_entry(
        db, user_id, books[1], EntryStatus.FINISHED,
        started_on=last_month() - timedelta(days=20), finished_on=last_month(), rating=Decimal("3"),
    )
    add_entry(db, user_id, books[2], EntryStatus.DROPPED)
    add_entry(db, user_id, books[3], EntryStatus.WANT)
    add_entry(db, user_id, show, EntryStatus.IN_PROGRESS)

    stats = client.get("/stats/me").json()

    assert stats["totals"] == {
        "entries": 5, "want": 1, "in_progress": 1, "finished": 2, "paused": 0, "dropped": 1,
    }
    assert stats["completion_rate"] == round(2 / 3, 3)
    assert stats["by_media_type"][0] == {"media_type": "book", "total": 4, "finished": 2}
    assert stats["by_media_type"][1] == {"media_type": "tv", "total": 1, "finished": 0}

    months = {m["month"]: m["count"] for m in stats["finished_per_month"]}
    assert months[today().strftime("%Y-%m")] == 1
    assert months[last_month().strftime("%Y-%m")] == 1
    assert sum(months.values()) == 2

    assert stats["average_days_to_finish"] == 15.0
    assert stats["average_rating"] == 3.75
    ratings = {bucket["rating"]: bucket["count"] for bucket in stats["rating_distribution"]}
    assert ratings[4.5] == 1 and ratings[3.0] == 1 and ratings[5.0] == 0
    assert stats["backlog"]["count"] == 1


def test_stats_never_include_other_users(db):
    me = logged_in_client("me@example.com")
    other = logged_in_client("other@example.com")
    work = add_catalogue_work(db)
    add_entry(db, current_user_id(other), work, EntryStatus.FINISHED, finished_on=today())

    stats = me.get("/stats/me").json()

    assert stats["totals"]["entries"] == 0
    assert sum(m["count"] for m in stats["finished_per_month"]) == 0

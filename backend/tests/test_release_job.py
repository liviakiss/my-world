import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.catalogue.base import CatalogueError, ReleaseInfo
from app.jobs.check_releases import check_releases
from app.models import (
    AnalyticsEvent, DataSource, DatePrecision, Follow, MediaType, Release, User, Work,
)

NOW = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
NEXT_EPISODE = ReleaseInfo(
    is_ongoing=True,
    total_units=24,
    next_label="Season 2, episode 1",
    next_date=date(2027, 1, 10),
    next_precision=DatePrecision.DAY,
)


class FakeChecker:
    source = DataSource.TMDB

    def __init__(self, answers: dict[str, ReleaseInfo | Exception | None]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def release_info(self, external_id: str) -> ReleaseInfo | None:
        self.calls.append(external_id)
        answer = self.answers.get(external_id)
        if isinstance(answer, Exception):
            raise answer
        return answer


def create_user(db, email: str) -> uuid.UUID:
    user = User(email=email, password_hash="not-used")
    db.add(user)
    db.commit()
    return user.id


def create_show(db, external_id: str, is_ongoing: bool | None = None, source=DataSource.TMDB) -> Work:
    work = Work(
        title=f"Show {external_id}",
        media_type=MediaType.ANIME,
        source=source,
        external_id=external_id,
        is_ongoing=is_ongoing,
    )
    db.add(work)
    db.commit()
    return work


def follow(db, user_id: uuid.UUID, work: Work) -> None:
    db.add(Follow(user_id=user_id, work_id=work.id))
    db.commit()


def run(db, checker: FakeChecker, now: datetime = NOW):
    result = check_releases(db, {DataSource.TMDB: checker}, now=now)
    db.expire_all()
    return result


def test_new_release_is_stored_and_every_follower_is_told(db):
    show = create_show(db, "tv:1")
    follow(db, create_user(db, "a@example.com"), show)
    follow(db, create_user(db, "b@example.com"), show)

    result = run(db, FakeChecker({"tv:1": NEXT_EPISODE}))

    assert (result.checked, result.found, result.failed) == (1, 1, 0)
    release = db.scalar(select(Release))
    assert release.label == "Season 2, episode 1"
    assert release.release_date == date(2027, 1, 10)
    assert show.is_ongoing is True and show.total_units == 24
    found_events = db.scalars(
        select(AnalyticsEvent).where(AnalyticsEvent.event_type == "release_found")
    ).all()
    assert len(found_events) == 2


def test_a_show_is_checked_at_most_once_per_interval(db):
    show = create_show(db, "tv:1")
    follow(db, create_user(db, "a@example.com"), show)
    checker = FakeChecker({"tv:1": NEXT_EPISODE})

    run(db, checker)
    run(db, checker, now=NOW + timedelta(hours=2))

    assert checker.calls == ["tv:1"]


def test_rechecking_updates_the_date_without_duplicates(db):
    show = create_show(db, "tv:1")
    follow(db, create_user(db, "a@example.com"), show)
    run(db, FakeChecker({"tv:1": NEXT_EPISODE}))

    moved = ReleaseInfo(
        is_ongoing=True,
        next_label="Season 2, episode 1",
        next_date=date(2027, 2, 1),
        next_precision=DatePrecision.DAY,
    )
    result = run(db, FakeChecker({"tv:1": moved}), now=NOW + timedelta(days=1))

    assert result.found == 0
    releases = db.scalars(select(Release)).all()
    assert len(releases) == 1
    assert releases[0].release_date == date(2027, 2, 1)


def test_unfollowed_ended_and_unsupported_works_are_skipped(db):
    user_id = create_user(db, "a@example.com")
    create_show(db, "tv:1")
    follow(db, user_id, create_show(db, "tv:2", is_ongoing=False))
    follow(db, user_id, create_show(db, "OL1W", source=DataSource.OPEN_LIBRARY))
    checker = FakeChecker({})

    result = run(db, checker)

    assert checker.calls == []
    assert result.checked == 0


def test_one_failure_does_not_stop_the_others(db):
    user_id = create_user(db, "a@example.com")
    broken = create_show(db, "tv:1")
    healthy = create_show(db, "tv:2")
    follow(db, user_id, broken)
    follow(db, user_id, healthy)
    checker = FakeChecker({"tv:1": CatalogueError("timeout"), "tv:2": NEXT_EPISODE})

    result = run(db, checker)

    assert (result.checked, result.found, result.failed) == (1, 1, 1)
    assert broken.last_checked_at == NOW

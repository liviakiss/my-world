import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.jobs.send_reminders import send_reminders
from app.models import (
    DataSource, DatePrecision, Follow, MediaType, Notification, Release, User, Work,
)
from tests.helpers import FakeEmailSender

NOW = datetime(2026, 11, 18, 7, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def create_user(db, email: str, verified: bool = True, **settings) -> uuid.UUID:
    user = User(email=email, password_hash="x", is_email_verified=verified, **settings)
    db.add(user)
    db.commit()
    return user.id


def create_show(db, title: str = "Frieren") -> Work:
    work = Work(
        title=title,
        media_type=MediaType.ANIME,
        source=DataSource.TMDB,
        external_id=f"tv:{uuid.uuid4().int % 10**9}",
        is_ongoing=True,
    )
    db.add(work)
    db.commit()
    return work


def add_release(db, work: Work, on: date, label: str = "Season 2, episode 1",
                precision: DatePrecision = DatePrecision.DAY, updated: datetime | None = None) -> None:
    release = Release(work_id=work.id, label=label, release_date=on, precision=precision,
                      source=DataSource.TMDB)
    db.add(release)
    db.commit()
    release.updated_at = updated or NOW - timedelta(days=10)
    db.commit()


def follow(db, user_id: uuid.UUID, work: Work, **manual) -> None:
    db.add(Follow(user_id=user_id, work_id=work.id, **manual))
    db.commit()


def run(db, sender: FakeEmailSender, now: datetime = NOW):
    return send_reminders(db, sender, now=now)


def test_release_day_email_goes_to_followers(db):
    show = create_show(db)
    add_release(db, show, TODAY)
    follow(db, create_user(db, "fan@example.com"), show)
    create_user(db, "stranger@example.com")
    sender = FakeEmailSender()

    result = run(db, sender)

    assert result.sent == 1
    [message] = sender.sent
    assert message.to == "fan@example.com"
    assert message.subject == "Out today: Frieren — Season 2, episode 1"


def test_each_reminder_is_sent_only_once(db):
    show = create_show(db)
    add_release(db, show, TODAY)
    follow(db, create_user(db, "fan@example.com"), show)
    sender = FakeEmailSender()

    run(db, sender)
    second = run(db, sender, now=NOW + timedelta(hours=3))

    assert len(sender.sent) == 1
    assert second.skipped == 1
    assert db.query(Notification).count() == 1


def test_unverified_and_opted_out_users_get_nothing(db):
    show = create_show(db)
    add_release(db, show, TODAY)
    follow(db, create_user(db, "unverified@example.com", verified=False), show)
    follow(db, create_user(db, "quiet@example.com", notify_email=False), show)
    sender = FakeEmailSender()

    run(db, sender)

    assert sender.sent == []


def test_day_before_only_when_switched_on(db):
    show = create_show(db)
    add_release(db, show, TODAY + timedelta(days=1))
    follow(db, create_user(db, "default@example.com"), show)
    follow(db, create_user(db, "early@example.com", notify_day_before=True), show)
    sender = FakeEmailSender()

    run(db, sender)

    assert [m.to for m in sender.sent] == ["early@example.com"]
    assert sender.sent[0].subject.startswith("Tomorrow:")


def test_my_own_date_drives_the_reminder(db):
    show = create_show(db)
    add_release(db, show, TODAY + timedelta(days=30))
    follow(db, create_user(db, "fan@example.com"), show,
           manual_release_date=TODAY, manual_release_label="Book 4")
    sender = FakeEmailSender()

    run(db, sender)

    assert sender.sent[0].subject == "Out today: Frieren — Book 4"


def test_vague_dates_never_trigger_release_day_emails(db):
    show = create_show(db)
    follow(db, create_user(db, "fan@example.com"), show,
           manual_release_date=TODAY, manual_release_precision=DatePrecision.MONTH)
    sender = FakeEmailSender()

    run(db, sender)

    assert sender.sent == []


def test_newly_found_dates_are_announced(db):
    show = create_show(db)
    add_release(db, show, TODAY + timedelta(days=20), updated=NOW - timedelta(hours=2))
    follow(db, create_user(db, "fan@example.com"), show)
    sender = FakeEmailSender()

    run(db, sender)

    assert sender.sent[0].subject == "New date: Frieren — Season 2, episode 1"


def test_failed_sends_are_retried_next_run(db):
    show = create_show(db)
    add_release(db, show, TODAY)
    follow(db, create_user(db, "fan@example.com"), show)

    failed = run(db, FakeEmailSender(fail=True))
    working = FakeEmailSender()
    retried = run(db, working, now=NOW + timedelta(hours=1))

    assert failed.failed == 1
    assert retried.sent == 1
    assert len(working.sent) == 1


def test_titles_cannot_inject_email_headers(db):
    show = create_show(db, title="Evil\r\nBcc: victim@example.com")
    add_release(db, show, TODAY)
    follow(db, create_user(db, "fan@example.com"), show)
    sender = FakeEmailSender()

    run(db, sender)

    assert "\n" not in sender.sent[0].subject
    assert "\r" not in sender.sent[0].subject

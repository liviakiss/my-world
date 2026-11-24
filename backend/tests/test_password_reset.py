from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import EmailToken, RefreshToken, SecurityEvent, SecurityEventType, TokenPurpose, User
from tests.helpers import TEST_PASSWORD, login, signup, token_from

EMAIL = "livia@example.com"
NEW_PASSWORD = "a-brand-new-long-password"


def forgot(client, email: str = EMAIL):
    return client.post("/auth/forgot-password", json={"email": email})


def reset(client, token: str, password: str = NEW_PASSWORD):
    return client.post("/auth/reset-password", json={"token": token, "new_password": password})


def reset_token(client, outbox) -> str:
    forgot(client)
    return token_from(outbox.to(EMAIL)[-1])


def test_unknown_and_known_emails_get_the_same_answer(client, outbox):
    signup(client, EMAIL)

    known = forgot(client)
    unknown = forgot(client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert outbox.to("nobody@example.com") == []
    assert "Reset your" in outbox.to(EMAIL)[-1].subject


def test_reset_changes_the_password_and_only_works_once(client, outbox):
    signup(client, EMAIL)
    token = reset_token(client, outbox)

    first = reset(client, token)
    second = reset(client, token, password="yet-another-long-password")

    assert first.status_code == 200
    assert second.status_code == 400
    assert login(client, EMAIL, password=TEST_PASSWORD).status_code == 401
    assert login(client, EMAIL, password=NEW_PASSWORD).status_code == 200


def test_reset_logs_out_every_session_and_unlocks(client, outbox, db):
    signup(client, EMAIL)
    login(client, EMAIL)
    for _ in range(5):
        login(client, EMAIL, password="wrong-password-here")
    token = reset_token(client, outbox)

    reset(client, token)

    assert all(t.revoked_at is not None for t in db.scalars(select(RefreshToken)))
    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user.locked_until is None
    assert user.is_email_verified is True
    assert "password was changed" in outbox.to(EMAIL)[-1].subject


def test_reset_links_expire_after_30_minutes(client, outbox, db):
    signup(client, EMAIL)
    token = reset_token(client, outbox)
    stored = db.scalar(select(EmailToken).where(EmailToken.purpose == TokenPurpose.RESET_PASSWORD))
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert reset(client, token).status_code == 400


def test_verification_tokens_cannot_reset_passwords(client, outbox):
    signup(client, EMAIL)
    verification_token = token_from(outbox.to(EMAIL)[0])

    assert reset(client, verification_token).status_code == 400


def test_short_new_password_is_rejected(client, outbox):
    signup(client, EMAIL)
    token = reset_token(client, outbox)

    assert reset(client, token, password="short").status_code == 422


def test_reset_requests_are_logged(client, outbox, db):
    signup(client, EMAIL)

    forgot(client)

    types = db.scalars(select(SecurityEvent.event_type)).all()
    assert SecurityEventType.PASSWORD_RESET_REQUESTED in types

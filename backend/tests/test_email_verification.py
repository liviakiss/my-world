from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import EmailToken, User
from tests.helpers import login, signup, token_from

EMAIL = "livia@example.com"


def verify(client, token: str):
    return client.post("/auth/verify-email", json={"token": token})


def test_signup_sends_a_confirmation_link(client, outbox):
    signup(client, EMAIL)

    [message] = outbox.to(EMAIL)
    assert "Confirm your email" in message.subject
    assert "http://localhost:3000/verify-email?token=" in message.text


def test_the_link_verifies_the_email_once(client, outbox, db):
    signup(client, EMAIL)
    token = token_from(outbox.to(EMAIL)[0])

    first = verify(client, token)
    second = verify(client, token)

    assert first.status_code == 200
    assert second.status_code == 400
    assert db.scalar(select(User.is_email_verified).where(User.email == EMAIL)) is True


def test_tokens_are_stored_only_as_hashes(client, outbox, db):
    signup(client, EMAIL)
    token = token_from(outbox.to(EMAIL)[0])

    stored = db.scalar(select(EmailToken))

    assert stored.token_hash != token
    assert len(stored.token_hash) == 64


def test_expired_and_made_up_tokens_are_rejected(client, outbox, db):
    signup(client, EMAIL)
    token = token_from(outbox.to(EMAIL)[0])
    stored = db.scalar(select(EmailToken))
    stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    assert verify(client, token).status_code == 400
    assert verify(client, "x" * 43).status_code == 400
    assert verify(client, "short").status_code == 422


def test_existing_email_gets_a_warning_instead_of_a_link(client, outbox):
    first = signup(client, EMAIL)
    second = signup(client, EMAIL, password="another-long-password")

    assert first.json() == second.json()
    messages = outbox.to(EMAIL)
    assert len(messages) == 2
    assert "tried to sign up" in messages[1].subject
    assert "token=" not in messages[1].text


def test_resending_replaces_the_old_link(client, outbox):
    signup(client, EMAIL)
    login(client, EMAIL)
    old_token = token_from(outbox.to(EMAIL)[0])

    response = client.post("/auth/resend-verification")
    new_token = token_from(outbox.to(EMAIL)[-1])

    assert response.status_code == 200
    assert verify(client, old_token).status_code == 400
    assert verify(client, new_token).status_code == 200


def test_resending_requires_login(client):
    assert client.post("/auth/resend-verification").status_code == 401


def test_email_failure_does_not_break_signup(client, outbox):
    outbox.fail = True

    response = signup(client, EMAIL)

    assert response.status_code == 202

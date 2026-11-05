from sqlalchemy import func, select

from app.models import AnalyticsEvent, User
from tests.helpers import signup


def count_users(db) -> int:
    return db.scalar(select(func.count()).select_from(User))


def test_signup_stores_argon2_hash_and_tracks_event(client, db):
    response = signup(client, "livia@example.com")

    assert response.status_code == 202
    user = db.scalar(select(User).where(User.email == "livia@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    event_types = db.scalars(select(AnalyticsEvent.event_type)).all()
    assert event_types == ["user_signed_up"]


def test_signup_with_taken_email_looks_identical(client, db):
    first = signup(client, "livia@example.com")
    second = signup(client, "livia@example.com", password="a-completely-different-one")

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert count_users(db) == 1


def test_signup_normalizes_email_case(client, db):
    signup(client, "livia@example.com")
    signup(client, "  Livia@Example.COM ")

    assert count_users(db) == 1


def test_short_password_is_rejected_without_echoing_it(client, db):
    response = client.post(
        "/auth/signup", json={"email": "livia@example.com", "password": "tiny-secret"}
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "password"
    assert "tiny-secret" not in response.text
    assert count_users(db) == 0


def test_invalid_email_is_rejected(client):
    response = client.post("/auth/signup", json={"email": "not-an-email", "password": "x" * 12})

    assert response.status_code == 422

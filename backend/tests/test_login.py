from sqlalchemy import select

from app.models import SecurityEvent, SecurityEventType, User
from tests.helpers import TEST_PASSWORD, login, signup

EMAIL = "livia@example.com"


def security_event_types(db) -> list[str]:
    return [event.value for event in db.scalars(select(SecurityEvent.event_type)).all()]


def test_login_sets_secure_cookies_and_returns_safe_user(client):
    signup(client, EMAIL)

    response = login(client, EMAIL)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == EMAIL
    assert "password_hash" not in body
    assert "failed_login_count" not in body

    set_cookies = response.headers.get_list("set-cookie")
    access = next(c for c in set_cookies if c.startswith("access_token="))
    refresh = next(c for c in set_cookies if c.startswith("refresh_token="))
    assert "HttpOnly" in access and "HttpOnly" in refresh
    assert "samesite=lax" in access.lower()
    assert "Path=/auth" in refresh


def test_me_works_only_after_login(client):
    signup(client, EMAIL)

    assert client.get("/auth/me").status_code == 401
    login(client, EMAIL)
    me = client.get("/auth/me")

    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_wrong_password_and_unknown_email_give_identical_errors(client):
    signup(client, EMAIL)

    wrong_password = login(client, EMAIL, password="not-the-right-password")
    unknown_email = login(client, "nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_five_failures_lock_the_account_even_for_the_right_password(client, db):
    signup(client, EMAIL)

    for _ in range(5):
        login(client, EMAIL, password="not-the-right-password")
    after_lock = login(client, EMAIL, password=TEST_PASSWORD)

    assert after_lock.status_code == 401
    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user.locked_until is not None
    assert SecurityEventType.ACCOUNT_LOCKED.value in security_event_types(db)


def test_successful_login_resets_failed_attempts(client, db):
    signup(client, EMAIL)
    login(client, EMAIL, password="not-the-right-password")
    login(client, EMAIL, password="not-the-right-password")

    login(client, EMAIL)

    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user.failed_login_count == 0


def test_security_events_store_hashed_ip_not_raw_ip(client, db):
    signup(client, EMAIL)
    login(client, EMAIL, password="not-the-right-password")

    event = db.scalar(select(SecurityEvent))
    assert event.event_type == SecurityEventType.LOGIN_FAILED
    assert len(event.ip_hash) == 64
    assert event.ip_hash != "testclient"

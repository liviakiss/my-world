from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import (
    AnalyticsEvent, Entry, RefreshToken, SecurityEvent, SecurityEventType, User, Work,
)
from tests.helpers import TEST_PASSWORD, add_catalogue_work, login, logged_in_client, signup, token_from

EMAIL = "livia@example.com"
NEW_PASSWORD = "a-brand-new-long-password"


def change_password(client, current: str = TEST_PASSWORD, new: str = NEW_PASSWORD):
    return client.post(
        "/auth/change-password", json={"current_password": current, "new_password": new}
    )


def second_device() -> TestClient:
    device = TestClient(app)
    login(device, EMAIL)
    return device


def test_changing_password_needs_the_current_one(db):
    client = logged_in_client(EMAIL)

    wrong = change_password(client, current="not-my-password")

    assert wrong.status_code == 400
    types = db.scalars(select(SecurityEvent.event_type)).all()
    assert SecurityEventType.REAUTH_FAILED in types


def test_changing_password_logs_out_other_devices_only(outbox):
    client = logged_in_client(EMAIL)
    other = second_device()

    response = change_password(client)

    assert response.status_code == 200
    assert client.post("/auth/refresh").status_code == 204
    assert other.post("/auth/refresh").status_code == 401
    assert "password was changed" in outbox.to(EMAIL)[-1].subject


def test_new_password_must_differ():
    client = logged_in_client(EMAIL)

    assert change_password(client, new=TEST_PASSWORD).status_code == 422


def test_logout_everywhere_revokes_every_session(db):
    client = logged_in_client(EMAIL)
    other = second_device()

    assert client.post("/auth/logout-all").status_code == 204
    assert other.post("/auth/refresh").status_code == 401
    assert all(t.revoked_at is not None for t in db.scalars(select(RefreshToken)))


def change_email(client, new_email: str, password: str = TEST_PASSWORD):
    return client.post("/me/email", json={"password": password, "new_email": new_email})


def test_email_change_needs_confirmation_from_the_new_inbox(outbox, db):
    client = logged_in_client(EMAIL)

    change_email(client, "New@Example.com")
    assert db.scalar(select(User.email)) == EMAIL

    token = token_from(outbox.to("new@example.com")[-1])
    confirmed = client.post("/auth/confirm-email-change", json={"token": token})

    assert confirmed.status_code == 200
    assert client.get("/auth/me").json()["email"] == "new@example.com"
    warning = outbox.to(EMAIL)[-1]
    assert "was changed" in warning.subject
    assert "n***@example.com" in warning.text


def test_email_change_does_not_reveal_taken_addresses(outbox):
    signup(TestClient(app), "taken@example.com")
    client = logged_in_client(EMAIL)

    taken = change_email(client, "taken@example.com")
    free = change_email(client, "free@example.com")

    assert taken.json() == free.json()
    assert [m.subject for m in outbox.to("taken@example.com")] == ["Confirm your email for My World"]


def test_email_change_needs_the_password():
    client = logged_in_client(EMAIL)

    assert change_email(client, "new@example.com", password="wrong-password").status_code == 400


def test_deleting_the_account_removes_personal_data_but_keeps_security_history(outbox, db):
    client = logged_in_client(EMAIL)
    work = add_catalogue_work(db)
    client.post("/entries", json={"work_id": str(work.id)})
    client.post("/works", json={"media_type": "book", "title": "My Private Book"})

    response = client.post("/me/delete", json={"password": TEST_PASSWORD})

    assert response.status_code == 204
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert db.scalar(select(func.count()).select_from(Entry)) == 0
    assert db.scalar(select(func.count()).select_from(AnalyticsEvent)) == 0
    assert db.scalar(select(Work.title).where(Work.title == "My Private Book")) is None
    assert db.scalar(select(Work.id).where(Work.id == work.id)) is not None
    deleted = db.scalar(
        select(SecurityEvent).where(SecurityEvent.event_type == SecurityEventType.ACCOUNT_DELETED)
    )
    assert deleted.user_id is None
    assert client.get("/auth/me").status_code == 401
    assert "was deleted" in outbox.to(EMAIL)[-1].subject


def test_deleting_needs_the_password(db):
    client = logged_in_client(EMAIL)

    assert client.post("/me/delete", json={"password": "wrong-password"}).status_code == 400
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_export_contains_my_data_and_no_secrets(db):
    client = logged_in_client(EMAIL)
    work = add_catalogue_work(db, title="Exported Book")
    entry_id = client.post("/entries", json={"work_id": str(work.id)}).json()["id"]
    client.patch(f"/entries/{entry_id}", json={"rating": 4.5, "notes": "lovely"})

    response = client.get("/me/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    data = response.json()
    assert data["account"]["email"] == EMAIL
    assert data["shelf"][0]["work"]["title"] == "Exported Book"
    assert data["shelf"][0]["rating"] == 4.5
    text = response.text
    assert "argon2" not in text
    assert "password" not in text
    assert "ip_hash" not in text


def test_export_never_includes_other_users(db):
    other = logged_in_client("other@example.com")
    work = add_catalogue_work(db, title="Their Book")
    other.post("/entries", json={"work_id": str(work.id)})
    me = logged_in_client(EMAIL)

    data = me.get("/me/export").json()

    assert data["shelf"] == []
    assert "Their Book" not in me.get("/me/export").text

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import logged_in_client


def test_defaults_are_email_on_day_before_off():
    client = logged_in_client("livia@example.com")

    assert client.get("/me/notifications").json() == {"email_enabled": True, "day_before": False}


def test_settings_can_be_changed_partly():
    client = logged_in_client("livia@example.com")

    client.patch("/me/notifications", json={"day_before": True})
    response = client.patch("/me/notifications", json={"email_enabled": False})

    assert response.json() == {"email_enabled": False, "day_before": True}


def test_settings_reject_unknown_fields_and_require_login():
    client = logged_in_client("livia@example.com")

    assert client.patch("/me/notifications", json={"role": "admin"}).status_code == 422
    assert TestClient(app).get("/me/notifications").status_code == 401

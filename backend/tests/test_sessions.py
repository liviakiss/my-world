from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models import RefreshToken, SecurityEvent, SecurityEventType
from tests.helpers import login, signup

EMAIL = "livia@example.com"


def logged_in(client: TestClient) -> TestClient:
    signup(client, EMAIL)
    login(client, EMAIL)
    return client


def refresh_with(token: str):
    return TestClient(app).post("/auth/refresh", headers={"Cookie": f"refresh_token={token}"})


def test_refresh_rotates_the_token(client, db):
    logged_in(client)
    old_token = client.cookies["refresh_token"]

    response = client.post("/auth/refresh")

    assert response.status_code == 204
    assert client.cookies["refresh_token"] != old_token
    tokens = db.scalars(select(RefreshToken)).all()
    assert len(tokens) == 2
    assert sum(token.revoked_at is not None for token in tokens) == 1


def test_reused_refresh_token_revokes_the_whole_family(client, db):
    logged_in(client)
    stolen_token = client.cookies["refresh_token"]
    client.post("/auth/refresh")

    attacker = refresh_with(stolen_token)
    victim = client.post("/auth/refresh")

    assert attacker.status_code == 401
    assert victim.status_code == 401
    assert all(token.revoked_at is not None for token in db.scalars(select(RefreshToken)))
    event_types = db.scalars(select(SecurityEvent.event_type)).all()
    assert SecurityEventType.REFRESH_TOKEN_REUSED in event_types


def test_unknown_refresh_token_is_rejected():
    assert refresh_with("made-up-token").status_code == 401


def test_logout_ends_the_session(client):
    logged_in(client)
    old_token = client.cookies["refresh_token"]

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert refresh_with(old_token).status_code == 401


def test_tampered_access_token_is_rejected():
    response = TestClient(app).get("/auth/me", headers={"Cookie": "access_token=not.a.jwt"})

    assert response.status_code == 401


def test_expired_access_token_is_rejected(client, db):
    logged_in(client)
    user_id = client.get("/auth/me").json()["id"]
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = jwt.encode(
        {"sub": user_id, "type": "access", "iat": past, "exp": past + timedelta(minutes=1)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    response = TestClient(app).get("/auth/me", headers={"Cookie": f"access_token={expired}"})

    assert response.status_code == 401


def test_token_signed_with_another_secret_is_rejected(client):
    logged_in(client)
    user_id = client.get("/auth/me").json()["id"]
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {"sub": user_id, "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        "attacker-guessed-secret-attacker-guessed-secret",
        algorithm="HS256",
    )

    response = TestClient(app).get("/auth/me", headers={"Cookie": f"access_token={forged}"})

    assert response.status_code == 401


def test_unsigned_alg_none_token_is_rejected(client):
    logged_in(client)
    user_id = client.get("/auth/me").json()["id"]
    now = datetime.now(timezone.utc)
    unsigned = jwt.encode(
        {"sub": user_id, "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        "",
        algorithm="none",
    )

    response = TestClient(app).get("/auth/me", headers={"Cookie": f"access_token={unsigned}"})

    assert response.status_code == 401

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.PyJWTError:
        return None

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except ValueError:
        return None


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

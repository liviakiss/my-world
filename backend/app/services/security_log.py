import hashlib
import hmac
import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SecurityEvent, SecurityEventType

USER_AGENT_MAX_LENGTH = 300


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    key = settings.ip_hash_secret.get_secret_value().encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def log_security_event(
    db: Session,
    request: Request,
    event_type: SecurityEventType,
    user_id: uuid.UUID | None = None,
) -> None:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:USER_AGENT_MAX_LENGTH] or None
    db.add(
        SecurityEvent(
            user_id=user_id,
            event_type=event_type,
            ip_hash=hash_ip(client_ip),
            user_agent=user_agent,
        )
    )

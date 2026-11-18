import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.tokens import hash_token
from app.models import EmailToken, TokenPurpose

VERIFY_EMAIL_LIFETIME = timedelta(hours=24)


def issue_email_token(
    db: Session, user_id: uuid.UUID, purpose: TokenPurpose, lifetime: timedelta
) -> str:
    now = datetime.now(timezone.utc)
    db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(32)
    db.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=now + lifetime,
        )
    )
    return token


def consume_email_token(db: Session, token: str, purpose: TokenPurpose) -> EmailToken | None:
    stored = db.scalar(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(token), EmailToken.purpose == purpose
        )
    )
    now = datetime.now(timezone.utc)
    if stored is None or stored.used_at is not None or stored.expires_at <= now:
        return None
    stored.used_at = now
    return stored

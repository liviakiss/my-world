import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.tokens import create_access_token, generate_refresh_token, hash_token
from app.config import settings
from app.models import RefreshToken


def issue_tokens(
    db: Session, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> tuple[str, str]:
    refresh_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        )
    )
    return create_access_token(user_id), refresh_token


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


def revoke_all_sessions(
    db: Session, user_id: uuid.UUID, keep_family: uuid.UUID | None = None
) -> None:
    query = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if keep_family is not None:
        query = query.where(RefreshToken.family_id != keep_family)
    db.execute(query.values(revoked_at=datetime.now(timezone.utc)))


def family_of(db: Session, refresh_token: str | None) -> uuid.UUID | None:
    if not refresh_token:
        return None
    return db.scalar(
        select(RefreshToken.family_id).where(RefreshToken.token_hash == hash_token(refresh_token))
    )

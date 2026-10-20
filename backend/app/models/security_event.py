# security_event.py — an append-only log of security-relevant actions.
# Used by: brute-force lockout logic, the admin security dashboard, incident review.
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SecurityEventType(str, enum.Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    ACCOUNT_LOCKED = "account_locked"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    EMAIL_CHANGED = "email_changed"
    REFRESH_TOKEN_REUSED = "refresh_token_reused"   # strong sign of a stolen token


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Nullable: failed logins for unknown emails have no user.
    # ondelete="SET NULL": deleting a user keeps the event but removes the link to them.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    event_type: Mapped[SecurityEventType] = mapped_column(
        Enum(
            SecurityEventType,
            native_enum=False,
            length=40,
            # same lesson as the users table: store values, not names
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,   # dashboards filter by type a lot ("all failed logins")
    )

    # SHA-256 hash of the IP (64 hex characters), never the raw IP → GDPR-friendly.
    ip_hash: Mapped[str | None] = mapped_column(String(64))

    # Browser info, cut to a safe length so nobody can fill the DB with a huge header.
    user_agent: Mapped[str | None] = mapped_column(String(300))

    # Indexed: almost every security query is "in the last X minutes/days".
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
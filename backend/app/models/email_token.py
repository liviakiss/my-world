import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import enum_values


class TokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(TokenPurpose, native_enum=False, length=30, values_callable=enum_values)
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

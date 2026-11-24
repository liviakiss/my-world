from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.models import SecurityEventType, User
from app.services.security_log import log_security_event

WRONG_PASSWORD_MESSAGE = "Your current password is incorrect."


def confirm_password(db: Session, request: Request, user: User, password: str) -> None:
    if user.password_hash is not None and verify_password(password, user.password_hash):
        return
    log_security_event(db, request, SecurityEventType.REAUTH_FAILED, user.id)
    db.commit()
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=WRONG_PASSWORD_MESSAGE)

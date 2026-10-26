from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.database import get_db
from app.models import User
from app.schemas.auth import MessageResponse, SignupRequest
from app.services.analytics import track_event

router = APIRouter(prefix="/auth", tags=["auth"])

SIGNUP_MESSAGE = "If this email can be registered, you will receive a confirmation email shortly."


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> MessageResponse:
    password_hash = hash_password(payload.password)

    email_taken = db.scalar(select(User.id).where(User.email == payload.email))
    if email_taken:
        return MessageResponse(message=SIGNUP_MESSAGE)

    user = User(email=payload.email, password_hash=password_hash)
    db.add(user)
    try:
        db.flush()
        track_event(db, user.id, "user_signed_up")
        db.commit()
    except IntegrityError:
        db.rollback()

    return MessageResponse(message=SIGNUP_MESSAGE)

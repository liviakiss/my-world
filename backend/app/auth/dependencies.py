from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.cookies import ACCESS_COOKIE
from app.auth.tokens import decode_access_token
from app.database import get_db
from app.models import User


def get_current_user(
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> User:
    user_id = decode_access_token(access_token) if access_token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user

from fastapi import Response

from app.config import settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/auth"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        ACCESS_COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )

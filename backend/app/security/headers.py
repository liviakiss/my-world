from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/openapi.json"}
API_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, enable_hsts: bool) -> None:
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers

        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"

        if request.url.path not in DOCS_PATHS:
            headers["Content-Security-Policy"] = API_CSP
            headers["Cache-Control"] = "no-store"

        if self.enable_hsts:
            headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response

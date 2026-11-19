"""HTTP-level protections: origin check (FR52), security headers (FR55), request size limit (FR57)
and generic error responses (FR58)."""

import logging
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .security import SAFE_METHODS, client_ip, security_log

log = logging.getLogger("onlineshop")

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
# FastAPI's interactive docs load their scripts from a CDN.
CSP_EXEMPT_PATHS = ("/docs", "/redoc")


def _error(status_code: int, message: str, code: str | None = None) -> JSONResponse:
    content = {"detail": message, "errors": [message]}
    if code:
        content["code"] = code
    return JSONResponse(status_code=status_code, content=content)


class RequestSizeLimit:
    """Reject bodies over the limit, by Content-Length up front or while streaming (FR57)."""

    MESSAGE = "The request is too large. The maximum upload size is 6 MB."

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await _error(413, self.MESSAGE)(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # HTTPException passes through FastAPI's body parsing unchanged.
                    raise StarletteHTTPException(413, self.MESSAGE)
            return message

        await self.app(scope, limited_receive, send)


def _same_origin(url: str, host: str) -> bool:
    return bool(host) and urlsplit(url).netloc.lower() == host.lower()


def install_web_security(app: FastAPI) -> None:
    settings = app.state.settings

    # Added before the middleware below so it sits inside it: errors raised while
    # streaming the body then reach FastAPI directly instead of being wrapped in an
    # ExceptionGroup by BaseHTTPMiddleware's task group.
    app.add_middleware(RequestSizeLimit, max_bytes=settings.max_request_bytes)

    @app.middleware("http")
    async def origin_check_and_headers(request: Request, call_next):
        if request.method not in SAFE_METHODS:
            host = request.headers.get("host", "")
            source = request.headers.get("origin") or request.headers.get("referer")
            if source is not None and not _same_origin(source, host):
                security_log.warning(
                    "origin_rejected ip=%s path=%s origin=%s", client_ip(request), request.url.path, source
                )
                response = _error(
                    403, "This request was rejected because it came from another website.", "origin_rejected"
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        headers = response.headers
        if not request.url.path.startswith(CSP_EXEMPT_PATHS):
            headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.cookie_secure:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error(500, "Something went wrong on our side. Please try again later.")

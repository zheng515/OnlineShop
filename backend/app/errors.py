"""Uniform error responses: every failure returns {"detail": str, "errors": [str]} (FR35)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ValidationProblem(Exception):
    def __init__(self, errors: list[str], status_code: int = 422):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.status_code = status_code


FIELD_MESSAGES = {
    "quantity": "Quantity must be a positive whole number.",
    "size": "Please select a valid size (S, M, L or XL).",
    "product_id": "A valid product must be selected.",
    "role": "Please choose either Administrator Login or Customer Login.",
    "username": "Username is required.",
    "password": "Password is required.",
    "source": "Checkout source must be 'cart' or 'buy_now'.",
}


def _readable(error: dict) -> str:
    field = next((str(part) for part in reversed(error.get("loc", ())) if isinstance(part, str)), "")
    if field in FIELD_MESSAGES:
        return FIELD_MESSAGES[field]
    if field and field != "body":
        return f"{field}: {error.get('msg', 'invalid value')}"
    if error.get("type") == "value_error":
        return str(error.get("msg", "")).removeprefix("Value error, ")
    return "The request could not be understood. Please check your input."


def _response(status_code: int, errors: list[str], headers=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": " ".join(errors), "errors": errors}, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValidationProblem)
    async def _validation_problem(_: Request, exc: ValidationProblem):
        return _response(exc.status_code, exc.errors)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError):
        messages = list(dict.fromkeys(_readable(err) for err in exc.errors()))
        return _response(422, messages)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return _response(exc.status_code, [detail], headers=getattr(exc, "headers", None))

"""Payment notifications from the provider (FR81) and the mock provider's own endpoints (FR84)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..database import Database, get_db
from ..payments.mock import MockProvider
from ..payments.provider import get_provider
from ..payments.service import handle_notification

router = APIRouter(tags=["payments"])


@router.post("/api/payments/webhooks/{provider_name}")
async def webhook(provider_name: str, request: Request, conn: Database = Depends(get_db)):
    """Server-to-server notification from the payment provider. Authenticated by its signature,
    not by a session, so it needs no login or CSRF token (FR81)."""
    body = await request.body()
    result = await run_in_threadpool(
        handle_notification, conn, request.app.state.settings, provider_name, dict(request.headers), body
    )
    return {"received": True, "result": result}


@router.get("/api/payments/info")
def payment_info(request: Request):
    """What the payment page tells the customer before they pay (FR32, FR79, FR84)."""
    settings = request.app.state.settings
    provider = get_provider(settings)
    return {
        "provider": provider.name,
        "method": provider.label,
        "test_mode": isinstance(provider, MockProvider),
        "currency": settings.currency,
        "timeout_minutes": settings.payment_timeout_minutes,
    }


# --- Mock provider (stands in for the provider's own website) ------------------


class MockOutcome(BaseModel):
    outcome: Literal["succeed", "fail", "cancel"]


def _mock(request: Request) -> MockProvider:
    provider = get_provider(request.app.state.settings)
    if not isinstance(provider, MockProvider):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The mock payment provider is not in use.")
    return provider


@router.get("/api/mock-provider/sessions/{reference}")
def mock_session(reference: str, request: Request, conn: Database = Depends(get_db)):
    session = _mock(request).session(conn, reference)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This payment session does not exist.")
    return session


@router.post("/api/mock-provider/sessions/{reference}/complete")
def mock_complete(reference: str, body: MockOutcome, request: Request, conn: Database = Depends(get_db)):
    provider = _mock(request)
    try:
        session, notification = provider.complete(conn, reference, body.outcome)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if notification is not None:
        # A real provider would POST this to /api/payments/webhooks/mock; the mock hands it to the
        # same handler directly, signature included.
        handle_notification(conn, request.app.state.settings, provider.name, provider.signed_headers(notification), notification)
    redirect = session["return_url"]
    if body.outcome == "cancel":
        # Like a provider's separate "cancel URL": the shop can tell the customer left without paying.
        redirect = redirect.replace("payment=returned", "payment=cancelled")
    return {"redirect_url": redirect}

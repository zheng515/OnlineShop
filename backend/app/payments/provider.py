"""The interface every payment provider implements (FR85).

Adding a real provider means writing one class with these methods and returning it from
`get_provider`; the order logic in app/payments/service.py stays the same.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ..config import Settings
from ..database import Database


@dataclass
class PaymentSession:
    reference: str  # the provider's id for this payment attempt
    url: str  # the provider's page where the customer pays


@dataclass
class PaymentNotification:
    event_id: str
    type: Literal["payment.succeeded", "payment.failed"]
    reference: str
    amount_cents: int
    currency: str
    reason: str | None = None


class InvalidNotification(Exception):
    """The notification's signature, timestamp or content is not acceptable (FR81)."""


class RefundFailed(Exception):
    """The provider did not refund the payment."""


class PaymentProvider(Protocol):
    name: str  # stored with each payment
    label: str  # shown to people, e.g. "Test card (mock provider)"

    def start(
        self,
        conn: Database,
        *,
        order_number: str,
        amount_cents: int,
        currency: str,
        expires_at: datetime,
        return_url: str,
    ) -> PaymentSession:
        """Create a payment attempt; the customer is sent to the returned URL."""

    def page_url(self, reference: str) -> str:
        """The provider page of an existing attempt."""

    def is_usable(self, conn: Database, reference: str) -> bool:
        """Whether the customer can still finish this attempt (not paid, failed, abandoned or expired)."""

    def parse_notification(self, headers: dict[str, str], body: bytes) -> PaymentNotification:
        """Verify a notification's signature and freshness and read it. Raises InvalidNotification."""

    def refund(self, conn: Database, reference: str, amount_cents: int) -> str:
        """Refund a paid attempt; returns the provider's refund reference. Raises RefundFailed."""


def get_provider(settings: Settings) -> PaymentProvider:
    if settings.payment_provider == "mock":
        from .mock import MockProvider

        return MockProvider(settings.payment_webhook_secret)
    raise RuntimeError(f"Unknown payment provider {settings.payment_provider!r} (SHOP_PAYMENT_PROVIDER).")

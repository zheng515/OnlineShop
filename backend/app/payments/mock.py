"""Built-in mock payment provider (FR84). It behaves like a hosted payment provider — its own payment
page, sessions that expire, signed notifications, refunds — but moves no money.

Its state lives in the mock_payment_sessions table. With a real provider that state is on the
provider's side, and the notification arrives as an HTTP request to /api/payments/webhooks/<name>;
the mock delivers it by calling the same handler directly.
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime

from ..database import Database
from ..security import utcnow
from .provider import InvalidNotification, PaymentNotification, PaymentSession, RefundFailed

SIGNATURE_HEADER = "mock-signature"
TIMESTAMP_TOLERANCE_SECONDS = 300  # FR81
MERCHANT_NAME = "OnlineShop"


def sign(secret: str, body: bytes, timestamp: int | None = None) -> str:
    """Signature header value: t=<unix time>,v1=<HMAC-SHA256 of "<t>.<body>">."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


class MockProvider:
    name = "mock"
    label = "Test card (mock provider)"

    def __init__(self, secret: str):
        self.secret = secret

    # --- Provider interface (FR85) -------------------------------------------------

    def start(self, conn: Database, *, order_number: str, amount_cents: int, currency: str,
              expires_at: datetime, return_url: str) -> PaymentSession:
        reference = f"mock_{secrets.token_urlsafe(18)}"
        conn.execute(
            """INSERT INTO mock_payment_sessions
               (reference, merchant_order, amount_cents, currency, return_url, status, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
            (reference, order_number, amount_cents, currency, return_url, expires_at.isoformat(), utcnow().isoformat()),
        )
        return PaymentSession(reference, self.page_url(reference))

    def page_url(self, reference: str) -> str:
        return f"/mock-pay.html?session={reference}"

    def is_usable(self, conn: Database, reference: str) -> bool:
        session = self.session(conn, reference)
        return bool(session) and session["status"] == "open" and session["seconds_left"] > 0

    def parse_notification(self, headers: dict[str, str], body: bytes) -> PaymentNotification:
        parts = dict(part.split("=", 1) for part in headers.get(SIGNATURE_HEADER, "").split(",") if "=" in part)
        try:
            timestamp = int(parts["t"])
            expected = sign(self.secret, body, timestamp).split("v1=", 1)[1]
            valid = hmac.compare_digest(expected, parts.get("v1", ""))
        except (KeyError, ValueError):
            valid = False
        if not valid:
            raise InvalidNotification("bad signature")
        if abs(time.time() - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
            raise InvalidNotification("stale timestamp")
        try:
            event = json.loads(body)
            data = event["data"]
            if event["type"] not in ("payment.succeeded", "payment.failed"):
                raise ValueError(event["type"])
            return PaymentNotification(
                event_id=str(event["id"]),
                type=event["type"],
                reference=str(data["reference"]),
                amount_cents=int(data["amount"]),
                currency=str(data["currency"]),
                reason=data.get("reason"),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidNotification("malformed notification") from exc

    def refund(self, conn: Database, reference: str, amount_cents: int) -> str:
        updated = conn.execute(
            """UPDATE mock_payment_sessions SET refunded_at = ?
               WHERE reference = ? AND status = 'succeeded' AND refunded_at IS NULL AND amount_cents = ?""",
            (utcnow().isoformat(), reference, amount_cents),
        ).rowcount
        conn.commit()
        if updated != 1:
            raise RefundFailed("The mock provider has no unrefunded payment with this reference and amount.")
        return f"mockrf_{secrets.token_urlsafe(12)}"

    # --- The provider's own side: its payment page (used by routers/mock_provider.py) --

    def session(self, conn: Database, reference: str) -> dict | None:
        row = conn.execute("SELECT * FROM mock_payment_sessions WHERE reference = ?", (reference,)).fetchone()
        if row is None:
            return None
        seconds_left = max(0, int((datetime.fromisoformat(row["expires_at"]) - utcnow()).total_seconds()))
        return {
            "reference": row["reference"],
            "merchant": MERCHANT_NAME,
            "order_number": row["merchant_order"],
            "amount": round(row["amount_cents"] / 100, 2),
            "amount_cents": row["amount_cents"],
            "currency": row["currency"],
            "status": row["status"],
            "seconds_left": seconds_left,
            "return_url": row["return_url"],
        }

    def complete(self, conn: Database, reference: str, outcome: str) -> tuple[dict, bytes | None]:
        """The customer chose an outcome on the mock page. Returns the session and, for a payment
        or a decline, the signed notification body to deliver to the shop."""
        session = self.session(conn, reference)
        if session is None:
            raise LookupError("This payment session does not exist.")
        if session["status"] != "open":
            raise PermissionError("This payment session is already finished.")
        if session["seconds_left"] <= 0:
            raise PermissionError("This payment session has expired. Return to the shop to see your order.")
        new_status = {"succeed": "succeeded", "fail": "failed", "cancel": "abandoned"}[outcome]
        updated = conn.execute(
            "UPDATE mock_payment_sessions SET status = ? WHERE reference = ? AND status = 'open'",
            (new_status, reference),
        ).rowcount
        conn.commit()
        if updated != 1:
            raise PermissionError("This payment session is already finished.")
        if new_status == "abandoned":
            return session, None  # leaving the page sends no notification
        event = {
            "id": f"evt_{secrets.token_urlsafe(12)}",
            "type": "payment.succeeded" if new_status == "succeeded" else "payment.failed",
            "created": int(time.time()),
            "data": {
                "reference": reference,
                "amount": session["amount_cents"],
                "currency": session["currency"],
                "reason": None if new_status == "succeeded" else "The card was declined (simulated).",
            },
        }
        return session, json.dumps(event, separators=(",", ":")).encode()

    def signed_headers(self, body: bytes) -> dict[str, str]:
        return {SIGNATURE_HEADER: sign(self.secret, body)}

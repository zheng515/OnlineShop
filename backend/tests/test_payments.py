"""Payments through the mock provider (FR78-FR87)."""

import json
import logging
import threading
import time
from datetime import timedelta

import pytest

from app import order_service, security
from app.jobs import expire_orders_once as run_once
from app.payments import mock as mock_module
from app.payments import service
from app.payments.mock import MockProvider, sign
from app.payments.provider import RefundFailed
from app.security import utcnow

from conftest import complete_mock_payment, create_product, db
from test_orders import place, stock_of


@pytest.fixture
def shirt(client, admin):
    return create_product(client, admin, price="12.50", stock={"M": 5}).json()


@pytest.fixture
def order(client, customer, shirt):
    """A buy-now order of 2 × 12.50 awaiting payment."""
    response = place(client, customer, 25.0, source="buy_now", product_id=shirt["id"], size="M", quantity=2)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def clock(monkeypatch):
    """Move the shop's and the mock provider's clock forward."""
    def advance(minutes: float):
        later = utcnow() + timedelta(minutes=minutes)
        for module in (security, order_service, service, mock_module):
            monkeypatch.setattr(module, "utcnow", lambda: later)
    return advance


def get(client, headers, order_id):
    return client.get(f"/api/orders/{order_id}", headers=headers).json()


def pay_now(client, headers, order_id):
    return client.post(f"/api/orders/{order_id}/pay", headers=headers)


def secret_of(client):
    return client.app.state.settings.payment_webhook_secret


def webhook(client, event: dict, secret=None, timestamp=None):
    secret = secret or secret_of(client)
    body = json.dumps(event).encode()
    return client.post("/api/payments/webhooks/mock", content=body,
                       headers={"mock-signature": sign(secret, body, timestamp), "content-type": "application/json"})


def success_event(reference, amount=2500, currency="USD", event_id="evt_test_1"):
    return {"id": event_id, "type": "payment.succeeded",
            "data": {"reference": reference, "amount": amount, "currency": currency}}


def reference_of(order):
    return order["payment_url"].split("session=", 1)[1]


# --- FR78 payment flow -------------------------------------------------------------


def test_successful_payment_marks_the_order_paid(client, customer, order):
    session = client.get(f"/api/mock-provider/sessions/{reference_of(order)}").json()
    assert (session["merchant"], session["order_number"], session["amount"]) == ("OnlineShop", order["number"], 25.0)

    result = complete_mock_payment(client, order["payment_url"])
    assert result.json() == {"redirect_url": f"/order.html?id={order['id']}&payment=returned"}
    paid = get(client, customer, order["id"])
    assert paid["status"] == "paid" and paid["paid_at"] and paid["seconds_left"] is None
    assert [(p["status"], p["provider"], p["amount"]) for p in paid["payments"]] == [("succeeded", "mock", 25.0)]
    last = paid["history"][-1]
    assert (last["status"], last["actor_role"], last["actor_name"]) == ("paid", "system", "payment provider")
    assert paid["allowed_actions"] == ["cancelled"]
    assert pay_now(client, customer, order["id"]).json()["detail"] == "This order has already been paid."


def test_the_unfinished_payment_page_is_reused(client, customer, order):
    assert pay_now(client, customer, order["id"]).json()["payment_url"] == order["payment_url"]
    assert len(get(client, customer, order["id"])["payments"]) == 1


def test_only_the_order_owner_can_pay(client, order):
    from conftest import login

    bob = login(client, "bob", "bob12345", "customer")
    assert pay_now(client, bob, order["id"]).status_code == 404


# --- FR80 payment attempts --------------------------------------------------------


def test_declined_payment_can_be_retried(client, customer, order):
    complete_mock_payment(client, order["payment_url"], "fail")
    after_decline = get(client, customer, order["id"])
    assert after_decline["status"] == "awaiting_payment"
    assert after_decline["payments"][0]["failure_reason"] == "The card was declined (simulated)."

    retry = pay_now(client, customer, order["id"]).json()["payment_url"]
    assert retry != order["payment_url"]
    complete_mock_payment(client, retry)
    paid = get(client, customer, order["id"])
    assert paid["status"] == "paid"
    assert [p["status"] for p in paid["payments"]] == ["succeeded", "failed"]


def test_abandoned_payment_page_is_replaced(client, customer, order):
    assert complete_mock_payment(client, order["payment_url"], "cancel").status_code == 200
    assert get(client, customer, order["id"])["status"] == "awaiting_payment"
    retry = pay_now(client, customer, order["id"]).json()["payment_url"]
    assert retry != order["payment_url"]
    payments = get(client, customer, order["id"])["payments"]
    assert [p["status"] for p in payments] == ["pending", "failed"]
    assert payments[1]["failure_reason"] == "The payment page was left without paying."
    # The abandoned page cannot be used any more.
    assert complete_mock_payment(client, order["payment_url"]).status_code == 409


def test_a_second_payment_for_a_paid_order_is_refunded(client, customer, order):
    complete_mock_payment(client, order["payment_url"])
    # A second attempt opened before the first was paid (another tab), paid afterwards.
    conn = db(client)
    provider = MockProvider(secret_of(client))
    session = provider.start(conn, order_number=order["number"], amount_cents=2500, currency="USD",
                             expires_at=utcnow() + timedelta(minutes=5), return_url="/x")
    conn.execute(
        """INSERT INTO payments (order_id, provider, reference, amount_cents, currency, status, created_at, updated_at)
           VALUES (?, 'mock', ?, 2500, 'USD', 'pending', 'now', 'now')""",
        (order["id"], session.reference),
    )
    conn.commit()
    conn.close()
    complete_mock_payment(client, session.url)

    paid = get(client, customer, order["id"])
    assert paid["status"] == "paid"
    assert [(r["status"], r["reason"], r["payment_reference"]) for r in paid["refunds"]] == [
        ("refunded", "Duplicate payment", session.reference)
    ]


# --- FR81 notifications --------------------------------------------------------------


def test_forged_stale_and_malformed_notifications_are_rejected(client, customer, order, caplog):
    event = success_event(reference_of(order))
    with caplog.at_level(logging.WARNING, logger="onlineshop.security"):
        assert webhook(client, event, secret="wrong-secret").status_code == 400
        assert webhook(client, event, timestamp=int(time.time()) - 301).status_code == 400
        no_signature = client.post("/api/payments/webhooks/mock", content=json.dumps(event).encode())
        assert no_signature.status_code == 400
        assert webhook(client, {"id": "x", "type": "payment.succeeded"}).status_code == 400
    assert caplog.text.count("payment_notification_rejected") == 4
    assert get(client, customer, order["id"])["status"] == "awaiting_payment"


def test_a_valid_notification_over_http_is_processed_once(client, customer, order):
    first = webhook(client, success_event(reference_of(order)))
    assert first.json() == {"received": True, "result": "order paid"}
    assert webhook(client, success_event(reference_of(order))).json()["result"] == "duplicate"
    assert get(client, customer, order["id"])["status"] == "paid"


def test_simultaneous_copies_of_a_notification_are_processed_once(client, customer, order):
    body = json.dumps(success_event(reference_of(order), event_id="evt_same")).encode()
    headers = {"mock-signature": sign(secret_of(client), body)}
    results = []

    def deliver():
        conn = db(client)
        try:
            results.append(service.handle_notification(conn, client.app.state.settings, "mock", headers, body))
        finally:
            conn.close()

    threads = [threading.Thread(target=deliver) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["duplicate"] * 4 + ["order paid"]
    events = get(client, customer, order["id"])["history"]
    assert [e["status"] for e in events].count("paid") == 1


def test_wrong_amount_or_currency_is_not_accepted(client, customer, order, caplog):
    with caplog.at_level(logging.WARNING, logger="onlineshop.security"):
        result = webhook(client, success_event(reference_of(order), amount=1, event_id="evt_a"))
    assert result.json()["result"] == "amount mismatch"
    assert "payment_amount_mismatch" in caplog.text
    current = get(client, customer, order["id"])
    assert current["status"] == "awaiting_payment"
    assert current["payments"][0]["failure_reason"] == "The confirmed amount did not match the order."


def test_unknown_payments_are_acknowledged(client):
    assert webhook(client, success_event("mock_nope")).json() == {"received": True, "result": "unknown payment"}


# --- FR79 deadline ------------------------------------------------------------------


def test_unpaid_orders_are_cancelled_at_the_deadline(client, admin, customer, shirt, order, clock):
    assert stock_of(client, admin, shirt["id"]) == {"M": 3}
    clock(29)
    assert run_once(client.app.state.settings) == 0
    clock(31)
    assert run_once(client.app.state.settings) == 1

    cancelled = get(client, customer, order["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["history"][-1]["actor_name"] == "payment deadline"
    assert cancelled["payments"][0]["status"] == "failed"
    assert stock_of(client, admin, shirt["id"]) == {"M": 5}
    assert "cancelled" in pay_now(client, customer, order["id"]).json()["detail"]
    assert complete_mock_payment(client, order["payment_url"]).json()["detail"].startswith("This payment session has expired")


def test_paying_after_the_deadline_is_refused_even_before_the_job_runs(client, customer, order, clock):
    clock(31)
    response = pay_now(client, customer, order["id"])
    assert response.status_code == 409
    assert "time to pay for this order has run out" in response.json()["detail"]
    assert get(client, customer, order["id"])["status"] == "cancelled"


def test_opening_an_overdue_order_cancels_it(client, customer, order, clock):
    clock(31)
    assert get(client, customer, order["id"])["status"] == "cancelled"


def test_payment_confirmed_after_cancellation_is_refunded(client, customer, order):
    client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    complete_mock_payment(client, order["payment_url"])  # the provider page was still open
    current = get(client, customer, order["id"])
    assert current["status"] == "cancelled"
    assert current["payments"][0]["status"] == "succeeded"
    assert [(r["status"], r["reason"]) for r in current["refunds"]] == [("refunded", "Paid after the order was cancelled")]


def test_confirmation_and_deadline_at_the_same_time_end_consistently(client, admin, customer, shirt):
    for attempt in range(5):
        order = place(client, customer, 12.5, source="buy_now", product_id=shirt["id"], size="M", quantity=1).json()
        conn = db(client)
        overdue = (utcnow() - timedelta(seconds=1)).isoformat()
        conn.execute("UPDATE orders SET expires_at = ? WHERE id = ?", (overdue, order["id"]))
        conn.commit()
        conn.close()
        body = json.dumps(success_event(reference_of(order), amount=1250, event_id=f"evt_race_{attempt}")).encode()

        def confirm(body=body):
            conn = db(client)
            headers = {"mock-signature": sign(secret_of(client), body)}
            try:
                service.handle_notification(conn, client.app.state.settings, "mock", headers, body)
            finally:
                conn.close()

        threads = [threading.Thread(target=confirm), threading.Thread(target=run_once, args=(client.app.state.settings,))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        final = get(client, customer, order["id"])
        refunds = [r["status"] for r in final["refunds"]]
        # Either the payment won (paid, nothing refunded) or the deadline did (cancelled, refunded).
        assert (final["status"], refunds) in (("paid", []), ("cancelled", ["refunded"])), final
        if final["status"] == "paid":
            client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    assert stock_of(client, admin, shirt["id"]) == {"M": 5}


# --- FR82 refunds -----------------------------------------------------------------


def test_cancelling_a_paid_order_refunds_it(client, admin, customer, shirt, order):
    complete_mock_payment(client, order["payment_url"])
    response = client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    assert response.json()["message"].endswith("The amount paid is being refunded.")
    cancelled = response.json()
    assert cancelled["status"] == "cancelled"
    assert [(r["status"], r["amount"], r["reason"]) for r in cancelled["refunds"]] == [("refunded", 25.0, "Order cancelled")]
    assert cancelled["refunds"][0]["reference"].startswith("mockrf_")
    assert stock_of(client, admin, shirt["id"]) == {"M": 5}
    assert client.post(f"/api/orders/{order['id']}/cancel", headers=customer).status_code == 409


def test_failed_refund_can_be_retried_by_an_administrator(client, admin, customer, order, monkeypatch):
    complete_mock_payment(client, order["payment_url"])
    original_refund = MockProvider.refund

    def failing_refund(self, conn, reference, amount_cents):
        raise RefundFailed("Provider unavailable (simulated).")

    monkeypatch.setattr(MockProvider, "refund", failing_refund)
    cancelled = client.post(f"/api/admin/orders/{order['id']}/status", json={"status": "cancelled"}, headers=admin).json()
    assert cancelled["refunds"][0]["status"] == "failed"
    assert cancelled["can_retry_refund"] is True
    assert get(client, customer, order["id"])["refunds"][0]["status_label"] == "Failed"

    retry_url = f"/api/admin/orders/{order['id']}/refunds/retry"
    assert client.post(retry_url, headers=admin).json()["message"] == "The refund failed again."
    monkeypatch.setattr(MockProvider, "refund", original_refund)
    retried = client.post(f"/api/admin/orders/{order['id']}/refunds/retry", headers=admin).json()
    assert retried["message"] == "The refund has been completed."
    assert retried["refunds"][0]["status"] == "refunded" and retried["can_retry_refund"] is False
    assert client.post(f"/api/admin/orders/{order['id']}/refunds/retry", headers=admin).status_code == 409
    assert client.post(f"/api/admin/orders/{order['id']}/refunds/retry", headers=customer).status_code == 403


def test_a_payment_is_never_refunded_twice(client, customer, order):
    complete_mock_payment(client, order["payment_url"])
    client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    conn = db(client)
    assert order_service.create_refunds(conn, order["id"], "again", "now") == []
    conn.close()


# --- FR87 orders from earlier versions ------------------------------------------------


def test_legacy_paid_orders_are_cancelled_without_refund(client, admin, customer, order):
    conn = db(client)
    conn.execute("UPDATE orders SET status = 'paid', expires_at = NULL WHERE id = ?", (order["id"],))
    conn.execute("DELETE FROM payments WHERE order_id = ?", (order["id"],))
    conn.commit()
    conn.close()
    shipped = client.post(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    assert shipped.status_code == 200
    product_id = order["items"][0]["product_id"]
    other = place(client, customer, 12.5, source="buy_now", product_id=product_id, size="M", quantity=1).json()
    conn = db(client)
    conn.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (other["id"],))
    conn.execute("DELETE FROM payments WHERE order_id = ?", (other["id"],))
    conn.commit()
    conn.close()
    cancelled = client.post(f"/api/orders/{other['id']}/cancel", headers=customer).json()
    assert cancelled["status"] == "cancelled" and cancelled["refunds"] == []
    assert cancelled["message"].endswith("has been cancelled.")


# --- FR84 mock provider -----------------------------------------------------------


def test_mock_provider_warning_at_startup(tmp_path, database_url, caplog):
    from fastapi.testclient import TestClient

    from app.config import PROJECT_ROOT, Settings
    from app.main import create_app

    settings = Settings(db_path=tmp_path / "db", database_url=database_url, upload_dir=tmp_path / "up",
                        frontend_dir=PROJECT_ROOT / "frontend", seed_demo_data=False)
    with caplog.at_level(logging.WARNING, logger="onlineshop.payments"), TestClient(create_app(settings)):
        pass
    assert "mock payment provider is in use" in caplog.text


def test_mock_session_endpoints_reject_unknown_and_finished_sessions(client, order):
    assert client.get("/api/mock-provider/sessions/mock_unknown").status_code == 404
    assert complete_mock_payment(client, "/mock-pay.html?session=mock_unknown").status_code == 404
    complete_mock_payment(client, order["payment_url"])
    assert complete_mock_payment(client, order["payment_url"]).json()["detail"] == "This payment session is already finished."


def test_the_notification_secret_is_random_unless_configured(monkeypatch):
    from app.config import load_settings

    monkeypatch.delenv("SHOP_PAYMENT_WEBHOOK_SECRET", raising=False)
    first, second = load_settings().payment_webhook_secret, load_settings().payment_webhook_secret
    assert first != second and len(first) >= 40
    monkeypatch.setenv("SHOP_PAYMENT_WEBHOOK_SECRET", "from-the-provider")
    assert load_settings().payment_webhook_secret == "from-the-provider"

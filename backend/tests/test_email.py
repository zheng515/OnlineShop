"""Email outbox and delivery (FR95), and order emails (FR96, FR97)."""

import threading
from datetime import timedelta
from email import message_from_bytes

from test_accounts import emails

from app.email import delivery
from app.email.delivery import FileSender, SmtpSender, send_due
from app.email.outbox import queue_email
from app.security import utcnow

from conftest import complete_mock_payment, create_product, db
from test_orders import place


class Collecting:
    def __init__(self, fail_times=0):
        self.sent, self.fail_times = [], fail_times

    def send(self, message):
        if self.fail_times:
            self.fail_times -= 1
            raise ConnectionError("SMTP server unavailable")
        self.sent.append(message)


def _queue(client, count=1):
    conn = db(client)
    for index in range(count):
        queue_email(conn, f"to{index}@example.com", "Subject", "Open {{SHOP_URL}}/order.html?id=1", "test")
    conn.commit()
    conn.close()


def test_emails_are_sent_with_the_public_address(client):
    _queue(client)
    sender = Collecting()
    conn = db(client)
    client.app.state.settings.public_url = "https://shop.example"
    assert send_due(conn, client.app.state.settings, sender) == 1
    assert send_due(conn, client.app.state.settings, sender) == 0
    conn.close()
    [message] = sender.sent
    assert message["To"] == "to0@example.com" and message["From"] == client.app.state.settings.email_from
    assert "https://shop.example/order.html?id=1" in message.get_content()
    assert emails(client)[0]["status"] == "sent"


def test_failed_deliveries_are_retried_then_given_up(client, monkeypatch, caplog):
    _queue(client)
    settings = client.app.state.settings
    sender = Collecting(fail_times=10)
    clock = [utcnow()]
    monkeypatch.setattr(delivery, "utcnow", lambda: clock[0])
    conn = db(client)
    for attempt in range(1, 6):
        assert send_due(conn, settings, sender) == 0
        row = emails(client)[0]
        assert row["attempts"] == attempt and "SMTP server unavailable" in row["last_error"]
        assert send_due(conn, settings, sender) == 0  # not due again yet
        clock[0] += timedelta(hours=2)
    conn.close()
    assert emails(client)[0]["status"] == "failed"
    assert "email_failed" in caplog.text


def test_a_retry_succeeds(client):
    _queue(client)
    sender = Collecting(fail_times=1)
    conn = db(client)
    send_due(conn, client.app.state.settings, sender)
    conn.execute("UPDATE email_outbox SET next_attempt_at = ?", (utcnow().isoformat(),))
    conn.commit()
    assert send_due(conn, client.app.state.settings, sender) == 1
    conn.close()
    assert len(sender.sent) == 1 and emails(client)[0]["attempts"] == 2


def test_several_processes_never_send_an_email_twice(client):
    _queue(client, count=15)
    sender = Collecting()

    def worker():
        conn = db(client)
        try:
            send_due(conn, client.app.state.settings, sender)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(m["To"] for m in sender.sent) == sorted(f"to{i}@example.com" for i in range(15))


def test_stale_claims_are_picked_up_again(client):
    _queue(client)
    conn = db(client)
    conn.execute("UPDATE email_outbox SET status = 'sending', claimed_at = ?", ((utcnow() - timedelta(minutes=11)).isoformat(),))
    conn.commit()
    assert send_due(conn, client.app.state.settings, Collecting()) == 1
    conn.close()


def test_file_backend_writes_eml_files(client, tmp_path):
    _queue(client)
    conn = db(client)
    send_due(conn, client.app.state.settings, FileSender(tmp_path / "mail"))
    conn.close()
    [file] = (tmp_path / "mail").glob("*.eml")
    message = message_from_bytes(file.read_bytes())
    assert message["To"] == "to0@example.com"


def test_smtp_backend(client, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append(("quit",))

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["To"]))

    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
    settings = client.app.state.settings
    settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password = "mail.example", 587, "shop", "secret"
    _queue(client)
    conn = db(client)
    send_due(conn, settings, SmtpSender(settings))
    conn.close()
    assert calls == [
        ("connect", "mail.example", 587), ("starttls",), ("login", "shop", "secret"), ("send", "to0@example.com"), ("quit",)
    ]


# --- Order emails (FR96) -------------------------------------------------------------


def _give_alice_an_email(client):
    conn = db(client)
    conn.execute("UPDATE users SET email = 'alice@example.com', email_verified_at = 'x' WHERE username = 'alice'")
    conn.commit()
    conn.close()


def test_order_emails_follow_the_order(client, admin, customer):
    _give_alice_an_email(client)
    shirt = create_product(client, admin, price="10", stock={"S": 5}).json()
    order = place(client, customer, 10.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()
    complete_mock_payment(client, order["payment_url"])
    client.post(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    kinds = [e["kind"] for e in emails(client, "alice@example.com")]
    assert kinds == ["order_awaiting_payment", "order_paid", "order_shipped"]
    placed = emails(client, "alice@example.com")[0]
    assert placed["subject"] == f"Order {order['number']}: please complete your payment"
    assert "$10.00" in placed["body"] and "30 minutes" in placed["body"]
    assert f"{{{{SHOP_URL}}}}/order.html?id={order['id']}" in placed["body"]


def test_cancellation_and_refund_emails(client, admin, customer):
    _give_alice_an_email(client)
    shirt = create_product(client, admin, price="10", stock={"S": 5}).json()
    order = place(client, customer, 10.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()
    complete_mock_payment(client, order["payment_url"])
    client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    by_kind = {e["kind"]: e for e in emails(client, "alice@example.com")}
    assert "cancelled at your request" in by_kind["order_cancelled"]["body"]
    assert "is being refunded" in by_kind["order_cancelled"]["body"]
    assert "We have refunded $10.00" in by_kind["refund_completed"]["body"]


def test_deadline_cancellation_email_and_no_email_without_address(client, admin, customer, monkeypatch):
    from app import order_service, security
    from app.jobs import expire_orders_once
    from app.payments import service

    from conftest import login

    _give_alice_an_email(client)
    shirt = create_product(client, admin, price="10", stock={"S": 5}).json()
    place(client, customer, 10.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1)
    bob = login(client, "bob", "bob12345", "customer")  # bob has no email address in the tests
    place(client, bob, 10.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1)

    later = utcnow() + timedelta(minutes=31)
    for module in (security, order_service, service):
        monkeypatch.setattr(module, "utcnow", lambda: later)
    assert expire_orders_once(client.app.state.settings) == 2
    cancelled = emails(client, "alice@example.com", "order_cancelled")
    assert "because the payment was not completed in time" in cancelled[0]["body"]
    assert all(e["to_address"] == "alice@example.com" for e in emails(client))

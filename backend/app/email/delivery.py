"""Sending outbox emails (FR95): SMTP, or files for development."""

import logging
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol

from ..config import Settings
from ..database import Database
from ..security import utcnow
from .outbox import SHOP_URL

log = logging.getLogger("onlineshop.email")

MAX_ATTEMPTS = 5
RETRY_DELAYS = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1)]
STALE_CLAIM = timedelta(minutes=10)  # a process that claimed an email and died
BATCH = 20


class Sender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class FileSender:
    """Development: write each email to a .eml file instead of sending it."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def send(self, message: EmailMessage) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        name = f"{utcnow().strftime('%Y%m%dT%H%M%S%f')}-{message['X-Outbox-Id']}.eml"
        (self.directory / name).write_bytes(bytes(message))


class SmtpSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, message: EmailMessage) -> None:
        s = self.settings
        context = ssl.create_default_context()
        if s.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=context)
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        with client:
            if s.smtp_security == "starttls":
                client.starttls(context=context)
            if s.smtp_username:
                client.login(s.smtp_username, s.smtp_password)
            client.send_message(message)


def get_sender(settings: Settings) -> Sender:
    if settings.email_backend == "smtp":
        return SmtpSender(settings)
    if settings.email_backend == "file":
        return FileSender(settings.email_dir)
    raise RuntimeError(f"Unknown email backend {settings.email_backend!r} (SHOP_EMAIL_BACKEND).")


def build_message(row, settings: Settings) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = row["to_address"]
    message["Subject"] = row["subject"]
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain="onlineshop.local")
    message["X-Outbox-Id"] = str(row["id"])
    message.set_content(row["body"].replace(SHOP_URL, settings.public_url))
    return message


def send_due(conn: Database, settings: Settings, sender: Sender | None = None) -> int:
    """Send emails that are due; returns how many were sent. Safe to run in several processes:
    each email is claimed with a guarded update before it is sent."""
    sender = sender or get_sender(settings)
    now = utcnow()
    conn.execute(
        "UPDATE email_outbox SET status = 'pending' WHERE status = 'sending' AND claimed_at < ?",
        ((now - STALE_CLAIM).isoformat(),),
    )
    due = conn.execute(
        "SELECT id FROM email_outbox WHERE status = 'pending' AND next_attempt_at <= ? ORDER BY id LIMIT ?",
        (now.isoformat(), BATCH),
    ).fetchall()
    conn.commit()
    sent = 0
    for item in due:
        claimed = conn.execute(
            "UPDATE email_outbox SET status = 'sending', claimed_at = ? WHERE id = ? AND status = 'pending'",
            (utcnow().isoformat(), item["id"]),
        ).rowcount
        conn.commit()
        if claimed != 1:
            continue  # another process is sending it
        row = conn.execute("SELECT * FROM email_outbox WHERE id = ?", (item["id"],)).fetchone()
        try:
            sender.send(build_message(row, settings))
        except Exception as exc:  # noqa: BLE001 - any delivery problem is retried
            attempts = row["attempts"] + 1
            final = attempts >= MAX_ATTEMPTS
            retry_at = utcnow() + RETRY_DELAYS[min(attempts - 1, len(RETRY_DELAYS) - 1)]
            conn.execute(
                """UPDATE email_outbox SET status = ?, attempts = ?, last_error = ?, next_attempt_at = ?, claimed_at = NULL
                   WHERE id = ?""",
                ("failed" if final else "pending", attempts, str(exc)[:500], retry_at.isoformat(), row["id"]),
            )
            conn.commit()
            (log.error if final else log.warning)(
                "email_%s id=%s kind=%s attempt=%s error=%s",
                "failed" if final else "retry", row["id"], row["kind"], attempts, exc,
            )
            continue
        conn.execute(
            "UPDATE email_outbox SET status = 'sent', attempts = attempts + 1, sent_at = ?, claimed_at = NULL WHERE id = ?",
            (utcnow().isoformat(), row["id"]),
        )
        conn.commit()
        sent += 1
        # Never log the body: it can contain account tokens (FR59).
        log.info("email_sent id=%s kind=%s", row["id"], row["kind"])
    return sent

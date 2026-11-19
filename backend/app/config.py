"""Application settings, overridable through environment variables."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

SIZES = ("S", "M", "L", "XL")


@dataclass
class Settings:
    db_path: Path
    upload_dir: Path
    frontend_dir: Path
    token_ttl_hours: int = 8
    max_image_bytes: int = 5 * 1024 * 1024
    max_request_bytes: int = 6 * 1024 * 1024
    # Demo accounts have publicly known passwords: never enable in production (FR54).
    seed_demo_data: bool = True
    # Set when served over HTTPS: marks cookies Secure and sends HSTS (FR56).
    cookie_secure: bool = False
    # sqlite:///path or postgresql://user:password@host/db; defaults to SQLite at db_path (FR68, FR70).
    database_url: str = ""
    # Apply pending migrations at start-up; turn off where migrations run separately (FR69).
    auto_migrate: bool = True
    # Payments (FR79, FR84-FR86). "mock" is the built-in test provider; it moves no money.
    payment_provider: str = "mock"
    payment_timeout_minutes: int = 30
    # Secret that payment notifications are signed with (FR81). A real provider supplies it;
    # without one, each server start picks a random secret, so nobody can forge notifications.
    # (The mock provider delivers its notifications inside the server, so it needs no fixed value.)
    payment_webhook_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    currency: str = "USD"
    # How often expired unpaid orders are cancelled; 0 turns the background job off (FR79).
    job_interval_seconds: int = 60
    # Email (FR95, FR99). "file" writes emails to email_dir instead of sending them (development);
    # "smtp" sends them through the SMTP server below.
    public_url: str = "http://localhost:8000"
    email_backend: str = "file"
    email_from: str = "OnlineShop <no-reply@example.com>"
    email_dir: Path = BACKEND_DIR / "data" / "mail"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # "starttls", "ssl" or "none"
    # How often the outbox is sent; 0 turns sending off (tests send explicitly).
    email_interval_seconds: int = 5

    def __post_init__(self) -> None:
        if not self.database_url:
            self.database_url = f"sqlite:///{Path(self.db_path).resolve()}"


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("SHOP_DB_PATH", BACKEND_DIR / "data" / "shop.db")),
        upload_dir=Path(os.environ.get("SHOP_UPLOAD_DIR", BACKEND_DIR / "uploads")),
        frontend_dir=Path(os.environ.get("SHOP_FRONTEND_DIR", PROJECT_ROOT / "frontend")),
        token_ttl_hours=int(os.environ.get("SHOP_TOKEN_TTL_HOURS", "8")),
        seed_demo_data=os.environ.get("SHOP_SEED_DEMO_DATA", "1") != "0",
        cookie_secure=os.environ.get("SHOP_COOKIE_SECURE", "0") == "1",
        database_url=os.environ.get("SHOP_DATABASE_URL", ""),
        auto_migrate=os.environ.get("SHOP_AUTO_MIGRATE", "1") != "0",
        payment_provider=os.environ.get("SHOP_PAYMENT_PROVIDER", "mock"),
        payment_timeout_minutes=int(os.environ.get("SHOP_PAYMENT_TIMEOUT_MINUTES", "30")),
        payment_webhook_secret=os.environ.get("SHOP_PAYMENT_WEBHOOK_SECRET") or secrets.token_urlsafe(32),
        currency=os.environ.get("SHOP_CURRENCY", "USD"),
        job_interval_seconds=int(os.environ.get("SHOP_JOB_INTERVAL_SECONDS", "60")),
        public_url=os.environ.get("SHOP_PUBLIC_URL", "http://localhost:8000").rstrip("/"),
        email_backend=os.environ.get("SHOP_EMAIL_BACKEND", "file"),
        email_from=os.environ.get("SHOP_EMAIL_FROM", "OnlineShop <no-reply@example.com>"),
        email_dir=Path(os.environ.get("SHOP_EMAIL_DIR", BACKEND_DIR / "data" / "mail")),
        smtp_host=os.environ.get("SHOP_SMTP_HOST", "localhost"),
        smtp_port=int(os.environ.get("SHOP_SMTP_PORT", "587")),
        smtp_username=os.environ.get("SHOP_SMTP_USERNAME", ""),
        smtp_password=os.environ.get("SHOP_SMTP_PASSWORD", ""),
        smtp_security=os.environ.get("SHOP_SMTP_SECURITY", "starttls"),
        email_interval_seconds=int(os.environ.get("SHOP_EMAIL_INTERVAL_SECONDS", "5")),
    )

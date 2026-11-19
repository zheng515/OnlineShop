"""Application settings, overridable through environment variables."""

import os
from dataclasses import dataclass
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


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("SHOP_DB_PATH", BACKEND_DIR / "data" / "shop.db")),
        upload_dir=Path(os.environ.get("SHOP_UPLOAD_DIR", BACKEND_DIR / "uploads")),
        frontend_dir=Path(os.environ.get("SHOP_FRONTEND_DIR", PROJECT_ROOT / "frontend")),
        token_ttl_hours=int(os.environ.get("SHOP_TOKEN_TTL_HOURS", "8")),
        seed_demo_data=os.environ.get("SHOP_SEED_DEMO_DATA", "1") != "0",
        cookie_secure=os.environ.get("SHOP_COOKIE_SECURE", "0") == "1",
    )

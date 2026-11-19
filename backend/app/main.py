"""FastAPI application entry point.

Run from the backend directory with:  uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .database import connect, init_schema
from .errors import install_error_handlers
from .routers import admin_orders, admin_products, auth, orders, shop
from .seed import accounts_with_demo_passwords, seed
from .web_security import install_web_security


def _configure_logging() -> None:
    logger = logging.getLogger("onlineshop")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    _configure_logging()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        conn = connect(settings.db_path)
        try:
            init_schema(conn)
            seed(conn, settings.upload_dir, settings.seed_demo_data)
            demo_accounts = accounts_with_demo_passwords(conn)
            if demo_accounts:
                logging.getLogger("onlineshop.security").warning(
                    "Accounts still use their public demo passwords: %s. Disable demo data and change "
                    "these passwords before going to production (python -m app.accounts set-password).",
                    ", ".join(demo_accounts),
                )
        finally:
            conn.close()
        yield

    app = FastAPI(title="OnlineShop", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    install_error_handlers(app)
    install_web_security(app)

    app.include_router(auth.router)
    app.include_router(admin_products.router)
    app.include_router(shop.router)
    app.include_router(orders.router)
    app.include_router(admin_orders.router)

    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
    # Mounted last so it never shadows the API routes.
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()

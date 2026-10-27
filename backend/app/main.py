"""FastAPI application entry point.

Run from the backend directory with:  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .database import connect, init_schema
from .errors import install_error_handlers
from .routers import admin_products, auth, shop
from .seed import seed


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        conn = connect(settings.db_path)
        try:
            init_schema(conn)
            seed(conn, settings.upload_dir, settings.seed_demo_data)
        finally:
            conn.close()
        yield

    app = FastAPI(title="OnlineShop", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    install_error_handlers(app)

    app.include_router(auth.router)
    app.include_router(admin_products.router)
    app.include_router(shop.router)

    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
    # Mounted last so it never shadows the API routes.
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()

"""Health check for load balancers and container orchestration (FR72)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..database import connect

router = APIRouter(tags=["health"])
log = logging.getLogger("onlineshop")


@router.get("/api/health")
def health(request: Request):
    try:
        conn = connect(request.app.state.settings.database_url)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - any failure means the database is unusable
        log.exception("Health check: database unreachable")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}

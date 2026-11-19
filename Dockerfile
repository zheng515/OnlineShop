# OnlineShop application image (FR71, FR77).
# Base image pinned by digest so the same commit always builds from the same base.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/requirements.txt backend/requirements.lock backend/
# Behind a TLS-inspecting proxy, pass its CA bundle as an optional build secret:
#   docker build --secret id=ca_bundle,src=/path/to/ca-bundle.crt .
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi \
    && pip install -r backend/requirements.txt -c backend/requirements.lock

COPY backend/ backend/
COPY frontend/ frontend/
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin shop \
    && mkdir -p /data/uploads \
    && chown -R shop:shop /data \
    && chmod +x backend/docker-entrypoint.sh

# Production defaults (FR54, FR56, FR70); docker-compose.yml supplies the database URL.
ENV SHOP_FRONTEND_DIR=/app/frontend \
    SHOP_UPLOAD_DIR=/data/uploads \
    SHOP_DB_PATH=/data/shop.db \
    SHOP_SEED_DEMO_DATA=0 \
    SHOP_COOKIE_SECURE=1 \
    SHOP_AUTO_MIGRATE=0 \
    FORWARDED_ALLOW_IPS=127.0.0.1

USER shop
WORKDIR /app/backend
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]

# Migrations run once here, before the workers start (FR69); workers then only check them.
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]

# Pinned to a digest-stable tag rather than 'latest' so a rebuild produces the same base.
FROM python:3.12-slim AS base

# Python behaves better in a container this way: no .pyc clutter on the read-only layers, and
# logs appear immediately instead of sitting in a buffer when the container is killed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# gosu lets the entrypoint drop from root to the requested PUID/PGID without needing setuid
# binaries or su; su-exec/gosu is the standard lightweight choice for this pattern.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    # The test-only dependencies have no business in a runtime image.
    && pip uninstall -y pytest pytest-asyncio pytest-cov responses httpx 2>/dev/null || true

COPY app/ ./app/
# Not needed to run (the app builds its Alembic config in code) — copied so `docker exec` into a
# running container can drive Alembic by hand when troubleshooting a migration.
COPY alembic.ini .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# App data (the SQLite database) mounts here.
VOLUME ["/config"]
ENV FRANCHISARR_CONFIG_DIR=/config

LABEL org.opencontainers.image.title="Franchisarr" \
      org.opencontainers.image.description="Finds films missing from your Plex collections and TV spin-offs you don't have" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/prophetizer/franchisarr"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://localhost:8000' + os.environ.get('BASE_URL','').rstrip('/') + '/health', timeout=3)" || exit 1

# Entrypoint runs as root just long enough to chown /config to PUID/PGID, then drops privileges
# (see PROJECT_PLAN.md technical challenge #19) — do not set USER here, the entrypoint does it.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

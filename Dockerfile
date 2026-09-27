# Pinned by digest so a rebuild produces the same base; Dependabot proposes digest updates
# weekly, so security fixes to the base image still arrive (as a reviewable pull request).
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS base

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

# Runtime dependencies only: the test suite's live in requirements-dev.txt. (This used to install
# everything and uninstall the test packages with `|| true`, which also hid a failed install.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
# (see docs/DESIGN.md technical challenge #19) — do not set USER here, the entrypoint does it.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

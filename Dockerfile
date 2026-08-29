FROM python:3.12-slim AS base

# gosu lets the entrypoint drop from root to the requested PUID/PGID without needing setuid
# binaries or su; su-exec/gosu is the standard lightweight choice for this pattern.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# App data (SQLite DB etc., once Phase 1 lands) mounts here.
VOLUME ["/config"]
ENV FRANCHISARR_CONFIG_DIR=/config

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://localhost:8000' + os.environ.get('BASE_URL','').rstrip('/') + '/health', timeout=3)" || exit 1

# Entrypoint runs as root just long enough to chown /config to PUID/PGID, then drops privileges
# (see PROJECT_PLAN.md technical challenge #19) — do not set USER here, the entrypoint does it.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

"""FastAPI application entrypoint.

Everything -- routes, static files, redirects -- is mounted under BASE_URL, so serving at
https://host/franchisarr/ is the same code path as serving at the root (technical challenge #10).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import __version__
from app.config import get_settings
from app.db import get_engine, run_migrations
from app.logging_config import configure_logging, register_secret
from app.services.settings_service import seed_settings_from_env
from app.templating import STATIC_DIR, build_templates

settings = get_settings()
templates = build_templates(settings.base_url)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    # Registered before anything else can log: from here on a token appearing anywhere in a log
    # line -- including one written by a third-party library -- is redacted.
    for secret in settings.secret_values():
        register_secret(secret)

    logger.info("Starting Franchisarr %s (base URL: %r)", __version__, settings.base_url or "/")

    run_migrations()
    with Session(get_engine()) as session:
        seed_settings_from_env(session, settings)

    yield


app = FastAPI(title="Franchisarr", version=__version__, lifespan=lifespan)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Liveness endpoint for Docker HEALTHCHECK / reverse-proxy monitoring. Unauthenticated."""
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


app.include_router(router, prefix=settings.base_url)

# Mounted under BASE_URL for the same reason the routes are: behind a subpath proxy, /static
# would not reach us.
app.mount(f"{settings.base_url}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

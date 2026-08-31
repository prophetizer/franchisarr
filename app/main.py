"""FastAPI application entrypoint.

Everything -- routes, static files, redirects -- is mounted under BASE_URL, so serving at
https://host/franchisarr/ is the same code path as serving at the root (technical challenge #10).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import __version__
from app.auth.dependencies import (
    CurrentUser,
    DbSession,
    LoginRequired,
    RequiredUser,
    login_redirect,
)
from app.auth.local_admin import seed_local_admin_from_env
from app.services.instance_service import seed_radarr_from_env
from app.clients.plex_client import PlexClient, PlexClientError
from app.config import get_settings
from app.db import get_engine, run_migrations
from app.logging_config import configure_logging, register_secret
from app.routes_api import router as api_router
from app.routes_movies import router as movies_router
from app.routes_auth import router as auth_router
from app.services import library_service
from app.services.auth_service import discover_machine_identifier
from app.services.settings_service import SettingKey, get_setting, seed_settings_from_env
from app.templating import STATIC_DIR, get_templates

settings = get_settings()

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
        seed_local_admin_from_env(session, settings)
        seed_radarr_from_env(session, settings)

    yield


app = FastAPI(title="Franchisarr", version=__version__, lifespan=lifespan)


@app.exception_handler(LoginRequired)
async def _login_required_handler(request: Request, exc: LoginRequired):
    """Browsers get sent to the login form rather than a bare 401 body."""
    return login_redirect(request)


router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Liveness endpoint for Docker HEALTHCHECK / reverse-proxy monitoring. Unauthenticated."""
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: DbSession, user: RequiredUser):
    # The library-selection step is part of first-run setup: until something is chosen there is
    # nothing for the rest of the app to work with.
    if not library_service.has_selection(session):
        return RedirectResponse(
            f"{settings.base_url}/libraries", status_code=status.HTTP_303_SEE_OTHER
        )

    from app.services import movie_gap_service

    gaps = movie_gap_service.collections_with_gaps(session, user.id)
    return get_templates().TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "libraries": library_service.enabled_libraries(session),
            "collections_with_gaps": len(gaps),
            "total_missing": sum(len(gap.missing) for gap in gaps),
        },
    )


@router.get("/libraries", response_class=HTMLResponse)
def libraries_form(request: Request, session: DbSession, user: RequiredUser):
    """Show the library checkboxes, refreshing the list from Plex when it's reachable."""
    error = None
    plex_url = get_setting(session, SettingKey.PLEX_URL)
    plex_token = get_setting(session, SettingKey.PLEX_TOKEN)

    if not (plex_url and plex_token):
        error = "No Plex connection is configured yet, so no libraries could be listed."
    else:
        try:
            client = PlexClient(plex_url, plex_token)
            library_service.sync_from_plex(session, client)
            # Learning the server's identity here is what makes Plex sign-in possible at all.
            discover_machine_identifier(session, client)
        except PlexClientError as exc:
            # Fall back to what was stored: an unreachable Plex must not make the page unusable,
            # or a user could be stuck unable to change their selection until Plex comes back.
            error = f"{exc}. Showing the libraries last seen."

    return get_templates().TemplateResponse(
        request,
        "libraries.html",
        {"user": user, "libraries": library_service.list_libraries(session), "error": error},
    )


@router.post("/libraries", response_class=HTMLResponse)
def libraries_save(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    keys: Annotated[list[str], Form()] = [],
):
    library_service.set_enabled_libraries(session, keys)
    return RedirectResponse(f"{settings.base_url}/", status_code=status.HTTP_303_SEE_OTHER)


app.include_router(router, prefix=settings.base_url)
app.include_router(auth_router, prefix=settings.base_url)
app.include_router(movies_router, prefix=settings.base_url)
app.include_router(api_router, prefix=settings.base_url)

# Mounted under BASE_URL for the same reason the routes are: behind a subpath proxy, /static
# would not reach us.
app.mount(f"{settings.base_url}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
from app.services.sonarr_instance_service import seed_sonarr_from_env
from app.clients.media_server import MediaServerError, MediaServerKind
from app.config import get_settings
from app.db import get_engine, run_migrations
from app.logging_config import configure_logging, register_secret
from app.routes_api import router as api_router
from app.routes_instances import router as instances_router
from app.routes_movies import router as movies_router
from app.routes_directors import router as directors_router
from app.routes_franchises import router as franchises_router
from app.routes_lists import router as lists_router
from app.routes_preferences import router as preferences_router
from app.routes_tv import router as tv_router
from app.routes_auth import router as auth_router
from app.services import library_service
from app.services.auth_service import discover_machine_identifier
from app.services import scheduler as scheduler_service
from app.services.settings_service import SettingKey, get_setting, seed_settings_from_env
from app.templating import STATIC_DIR, get_templates

settings = get_settings()

logger = logging.getLogger(__name__)


def _discover_plex_server(session: Session) -> None:
    """Learn which Plex server this install is for, at startup.

    Plex sign-in is refused unless the account can reach *this* server, which means knowing the
    server's machine identifier. That was previously only learned when someone opened the library
    page -- a page you have to be signed in to reach. So Plex sign-in could never appear on a
    fresh install, and an install configured with Plex but no local admin had no way in at all.

    Failure is not fatal: an unreachable Plex simply leaves Plex sign-in unavailable until the
    next restart, which is the same conservative outcome as before.
    """
    from app.services import media_server_service

    if media_server_service.kind(session) != MediaServerKind.PLEX:
        return  # the server-identity check is a Plex sign-in concern only
    client = media_server_service.client_for(session)
    if client is None:
        return

    identifier = discover_machine_identifier(session, client)
    if identifier:
        logger.info("Plex sign-in is available")
    else:
        logger.warning(
            "Could not reach Plex at startup, so Plex sign-in stays unavailable until the next "
            "restart. The local admin account is unaffected."
        )


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
        seed_sonarr_from_env(session, settings)
        _discover_plex_server(session)
        scheduler_service.start(session)

    yield

    scheduler_service.shutdown()


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

    from datetime import date

    from app.services import movie_gap_service, tv_spinoff_service, upcoming_service

    gaps = movie_gap_service.collections_with_gaps(session, user.id)
    today = date.today()
    upcoming = upcoming_service.upcoming_films(session, user.id, today=today)
    upcoming_soon = sum(
        1 for f in upcoming
        if f.days_until(today) is not None and 0 <= f.days_until(today) <= 90
    )
    return get_templates().TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "libraries": library_service.enabled_libraries(session),
            "collections_with_gaps": len(gaps),
            "total_missing": sum(len(gap.missing) for gap in gaps),
            "spinoff_count": len(tv_spinoff_service.missing_spinoffs(session, user.id)),
            "upcoming_count": len(upcoming),
            "upcoming_soon": upcoming_soon,
            # Scanning is the thing the whole app depends on, so its control belongs on the page
            # people land on -- it used to live only on the collections page. Progress itself
            # comes from a context processor, since several pages show it now.
            "scanned": bool(movie_gap_service.owned_tmdb_ids(session)),
        },
    )


@router.get("/libraries", response_class=HTMLResponse)
def libraries_form(request: Request, session: DbSession, user: RequiredUser):
    """Show the library checkboxes, refreshing the list from Plex when it's reachable."""
    error = None
    from app.services import media_server_service

    client = media_server_service.client_for(session)
    if client is None:
        error = (f"{media_server_service.missing_message(session)[:-1]}, "
                 "so no libraries could be listed.")
    else:
        try:
            library_service.sync_from_plex(session, client)
            # Learning the server's identity here is what makes Plex sign-in possible at all.
            if client.kind == MediaServerKind.PLEX:
                discover_machine_identifier(session, client)
        except MediaServerError as exc:
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
    # First run: one skippable page of taste settings, each with an example. Never shown twice.
    from app.routes_preferences import preferences_reviewed

    if keys and not preferences_reviewed(session):
        return RedirectResponse(
            f"{settings.base_url}/preferences?first=1", status_code=status.HTTP_303_SEE_OTHER
        )
    return RedirectResponse(f"{settings.base_url}/", status_code=status.HTTP_303_SEE_OTHER)


app.include_router(router, prefix=settings.base_url)
app.include_router(auth_router, prefix=settings.base_url)
app.include_router(movies_router, prefix=settings.base_url)
app.include_router(instances_router, prefix=settings.base_url)
app.include_router(tv_router, prefix=settings.base_url)
app.include_router(franchises_router, prefix=settings.base_url)
app.include_router(directors_router, prefix=settings.base_url)
app.include_router(preferences_router, prefix=settings.base_url)
app.include_router(lists_router, prefix=settings.base_url)
app.include_router(api_router, prefix=settings.base_url)

# Mounted under BASE_URL for the same reason the routes are: behind a subpath proxy, /static
# would not reach us.
app.mount(f"{settings.base_url}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def html_is_never_stale(request, call_next):  # noqa: ANN001 - Starlette signature
    """Pages must be revalidated on every load.

    Static assets carry the app version in their URL, so a new release is a new URL. That only
    helps if the *page* that links them is fresh too -- and Safari on a phone was found holding
    a page from before a deploy, still pointing at the previous stylesheet. no-cache means
    "ask before reusing", which is exactly the deal for a server-rendered page.
    """
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response

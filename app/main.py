"""FastAPI application entrypoint.

Everything -- routes, static files, redirects -- is mounted under BASE_URL, so serving at
https://host/franchisarr/ is the same code path as serving at the root (technical challenge #10).
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import __version__
from app.auth.dependencies import (
    AdminUser,
    CurrentUser,
    DbSession,
    LoginRequired,
    RequiredUser,
    login_redirect,
)
from app.auth.local_admin import seed_local_admin_from_env
from app.services.instance_service import seed_radarr_from_env
from app.services.sonarr_instance_service import seed_sonarr_from_env

from app.config import get_settings
from app.db import get_engine, run_migrations
from app.logging_config import configure_logging, register_secret
from app.routes_api import router as api_router
from app.routes_instances import router as instances_router
from app.routes_movies import router as movies_router
from app.routes_directors import router as directors_router
from app.routes_franchises import router as franchises_router
from app.routes_lists import router as lists_router
from app.routes_media_servers import router as media_servers_router
from app.routes_preferences import router as preferences_router
from app.routes_tv import router as tv_router
from app.routes_auth import router as auth_router
from app.services import library_service, media_server_service, seerr_instance_service
from app.services.auth_service import discover_machine_identifier
from app.services import scheduler as scheduler_service
from app.services.settings_service import SECRET_KEYS, SettingKey, get_setting, seed_settings_from_env
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

    for server in media_server_service.plex_servers(session):
        client = media_server_service.client_for(server)
        identifier = discover_machine_identifier(session, server, client)
        if identifier:
            logger.info("Plex sign-in is available through %r", server.name)
        else:
            logger.warning(
                "Could not reach Plex server %r at startup, so Plex sign-in through it stays "
                "unavailable until the next restart. The local admin account is unaffected.",
                server.name,
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
        media_server_service.seed_from_env(session, settings)
        # Every stored credential is registered with the log redactor before anything else can
        # log it -- create/update register as they go, but rows that already exist would
        # otherwise stay unregistered until first used.
        for server in media_server_service.list_servers(session):
            register_secret(server.credential)
        for seerr in seerr_instance_service.list_seerr(session):
            register_secret(seerr.api_key)
        for key in SECRET_KEYS:
            register_secret(get_setting(session, key))
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


@router.get("/manifest.webmanifest")
def manifest() -> Response:
    """Web app manifest, so a phone can put Franchisarr on its home screen with the icon.

    A route rather than a static file because start_url and the icon paths depend on BASE_URL.
    Unauthenticated: browsers fetch it without cookies on some platforms, and it holds nothing.
    """
    from app.templating import make_asset_builder, make_url_builder

    base = get_settings().base_url
    url, asset = make_url_builder(base), make_asset_builder(base)
    document = {
        "name": "Franchisarr",
        "short_name": "Franchisarr",
        "description": "The films and shows missing from the sets you already own.",
        "start_url": url("/"),
        "scope": url("/"),
        "display": "standalone",
        "background_color": "#2e3440",
        "theme_color": "#2e3440",
        "icons": [
            {"src": asset("/static/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": asset("/static/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": asset("/static/icon.svg"), "sizes": "any", "type": "image/svg+xml"},
        ],
    }
    return Response(json.dumps(document), media_type="application/manifest+json")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: DbSession, user: RequiredUser):
    # The library-selection step is part of first-run setup: until something is chosen there is
    # nothing for the rest of the app to work with. Only an admin can choose, so only an admin is
    # sent there; a member sees the (empty) home page rather than a page they can't open.
    if user.is_admin and not library_service.has_selection(session):
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
def libraries_form(request: Request, session: DbSession, user: AdminUser):
    """Show the library checkboxes, per server, refreshing each list when its server is up."""
    from app.services import media_server_service

    groups = library_service.sync_all(session)
    return get_templates().TemplateResponse(
        request,
        "libraries.html",
        {"user": user, "groups": groups,
         "no_servers": not media_server_service.is_configured(session),
         "libraries": [lib for group in groups for lib in group.libraries]},
    )


@router.post("/libraries", response_class=HTMLResponse)
def libraries_save(
    request: Request,
    session: DbSession,
    user: AdminUser,
    keys: Annotated[list[int], Form()] = [],
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
app.include_router(media_servers_router, prefix=settings.base_url)
app.include_router(tv_router, prefix=settings.base_url)
app.include_router(franchises_router, prefix=settings.base_url)
app.include_router(directors_router, prefix=settings.base_url)
app.include_router(preferences_router, prefix=settings.base_url)
app.include_router(lists_router, prefix=settings.base_url)
app.include_router(api_router, prefix=settings.base_url)

# Mounted under BASE_URL for the same reason the routes are: behind a subpath proxy, /static
# would not reach us.
app.mount(f"{settings.base_url}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Outermost first: a too-large body or a cross-site post is refused before anything reads it.
from app.hardening import BodySizeLimit, CrossSiteGuard, SecurityHeaders  # noqa: E402

app.add_middleware(SecurityHeaders)
app.add_middleware(CrossSiteGuard)
app.add_middleware(BodySizeLimit)


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

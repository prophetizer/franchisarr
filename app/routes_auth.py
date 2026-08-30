"""Login, logout, and the Plex sign-in endpoints.

Plex sign-in uses a popup plus polling rather than plex.tv's forwardUrl redirect. A redirect
would need an absolute callback URL, which behind a reverse proxy at a subpath means trusting
X-Forwarded-* headers to reconstruct correctly -- a common source of "works locally, breaks
behind nginx". Polling needs no such reconstruction, and the browser never leaves our origin.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth import plex_oauth
from app.auth.dependencies import CurrentUser, DbSession
from app.auth.local_admin import authenticate_local, has_local_admin
from app.auth.sessions import COOKIE_NAME, SESSION_LIFETIME, create_session, delete_session
from app.config import get_settings
from app.services.auth_service import (
    PlexAccessDenied,
    get_machine_identifier,
    get_or_create_client_id,
    sign_in_with_plex_token,
)
from app.templating import get_templates

logger = logging.getLogger(__name__)

router = APIRouter()

#: Where the PIN id is parked between starting sign-in and polling for its result. A cookie keeps
#: this stateless; it is not a credential, and it is short-lived.
PIN_COOKIE = "franchisarr_plex_pin"


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


def _cookie_kwargs() -> dict:
    settings = get_settings()
    return {
        "httponly": True,
        "samesite": "lax",
        # Scoped to the base path so two apps behind the same hostname don't overwrite each
        # other's session cookie.
        "path": f"{settings.base_url}/" if settings.base_url else "/",
        "secure": settings.session_cookie_secure,
    }


def _set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        **_cookie_kwargs(),
    )


def _safe_next(raw: str | None) -> str:
    """Only ever redirect to a path inside this app.

    An unchecked `next` is an open redirect: a link to our own login page could bounce the user
    to an attacker's site wearing our hostname. Anything not a simple in-app path goes home.
    """
    base_url = get_settings().base_url
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return _url("/")
    if base_url and not raw.startswith(f"{base_url}/"):
        return _url("/")
    return raw


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: DbSession, user: CurrentUser, next: str | None = None):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)

    return get_templates().TemplateResponse(
        request,
        "login.html",
        {
            "next": next or "",
            "local_login_available": has_local_admin(session),
            "plex_login_available": get_machine_identifier(session) is not None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    session: DbSession,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
):
    user = authenticate_local(session, username, password)
    if user is None:
        # One message for both causes: saying which was wrong tells an attacker which usernames
        # exist.
        return get_templates().TemplateResponse(
            request,
            "login.html",
            {
                "error": "Incorrect username or password.",
                "next": next,
                "local_login_available": has_local_admin(session),
                "plex_login_available": get_machine_identifier(session) is not None,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_session(session, user)
    response = RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, token)
    return response


@router.post("/logout")
@router.get("/logout")
def logout(request: Request, session: DbSession):
    delete_session(session, request.cookies.get(COOKIE_NAME))
    response = RedirectResponse(_url("/login"), status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME, path=_cookie_kwargs()["path"])
    return response


@router.post("/auth/plex/start")
def plex_start(session: DbSession):
    """Create a sign-in PIN and hand back the app.plex.tv URL for the popup."""
    if get_machine_identifier(session) is None:
        return JSONResponse(
            {
                "error": "Plex sign-in isn't available until this install's Plex server "
                         "connection is configured.",
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    client_id = get_or_create_client_id(session)
    try:
        pin = plex_oauth.create_pin(client_id)
    except plex_oauth.PlexOAuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_502_BAD_GATEWAY)

    response = JSONResponse({"auth_url": plex_oauth.build_auth_url(client_id, pin.code)})
    response.set_cookie(PIN_COOKIE, str(pin.id), max_age=900, **_cookie_kwargs())
    return response


@router.post("/auth/plex/poll")
def plex_poll(request: Request, session: DbSession, next: Annotated[str, Form()] = ""):
    """Has the user finished signing in at plex.tv yet?"""
    raw_pin = request.cookies.get(PIN_COOKIE)
    if not raw_pin or not raw_pin.isdigit():
        return JSONResponse(
            {"error": "This sign-in attempt expired. Please start again."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    client_id = get_or_create_client_id(session)
    try:
        token = plex_oauth.check_pin(client_id, int(raw_pin))
    except plex_oauth.PlexOAuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_502_BAD_GATEWAY)

    if token is None:
        return JSONResponse({"status": "pending"})

    try:
        user = sign_in_with_plex_token(session, token)
    except PlexAccessDenied as exc:
        # Expected and important: a valid Plex account that isn't allowed on this server.
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except plex_oauth.PlexOAuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_502_BAD_GATEWAY)

    session_token = create_session(session, user)
    response = JSONResponse({"status": "ok", "redirect": _safe_next(next or None)})
    _set_session_cookie(response, session_token)
    response.delete_cookie(PIN_COOKIE, path=_cookie_kwargs()["path"])
    return response

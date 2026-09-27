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

from app.auth import plex_oauth, plex_pins
from app.auth.dependencies import CurrentUser, DbSession
from app.auth.local_admin import authenticate_local, has_local_admin
from app.auth.sessions import COOKIE_NAME, SESSION_LIFETIME, create_session, delete_session
from app.config import get_settings
from app.services.auth_service import (
    MemberSignInDisabled,
    PlexAccessDenied,
    plex_sign_in_available,
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
    # Browsers read a backslash as a slash, so "/\\evil.com" is "//evil.com" to them; control
    # characters (tab, newline) are stripped by the URL parser and can hide the same trick. The
    # server-side redirect happened to escape these, but the Plex flow hands `next` to
    # JavaScript as-is -- so refuse them outright rather than rely on who encodes what.
    if "\\" in raw or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return _url("/")
    if base_url and not raw.startswith(f"{base_url}/"):
        return _url("/")
    return raw


def _login_context(session, *, next: str = "", error: str | None = None) -> dict:  # noqa: ANN001
    """What the login page needs: which sign-in routes this install offers.

    Plex signs in by PIN and needs the server's identity known first; Jellyfin and Emby sign in
    with the person's own username and password on that server, so all they need is a URL.
    """
    from app.services import media_server_service

    password_servers = media_server_service.password_servers(session)
    return {
        "next": next,
        "error": error,
        "local_login_available": has_local_admin(session),
        "plex_login_available": plex_sign_in_available(session),
        "plex_configured": bool(media_server_service.plex_servers(session)),
        "server_login_available": bool(password_servers),
        # One server: its name is the heading. Several: a choice, so the person picks which
        # account they are typing.
        "password_servers": password_servers,
        "server_label": (media_server_service.label(password_servers[0].kind)
                         if len(password_servers) == 1 else "Jellyfin or Emby"),
        "server_name": password_servers[0].name if len(password_servers) == 1 else None,
    }


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: DbSession, user: CurrentUser, next: str | None = None):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)

    return get_templates().TemplateResponse(request, "login.html", _login_context(session, next=next or ""))


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    session: DbSession,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
):
    from app.hardening import client_key, login_limiter, username_key, username_limiter

    key, name_key = client_key(request), username_key(username)
    login_limiter.check(key)
    username_limiter.check(name_key)
    user = authenticate_local(session, username, password)
    if user is None:
        login_limiter.failed(key)
        username_limiter.failed(name_key)
        # One message for both causes: saying which was wrong tells an attacker which usernames
        # exist.
        return get_templates().TemplateResponse(
            request, "login.html",
            _login_context(session, next=next, error="Incorrect username or password."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    login_limiter.succeeded(key)
    username_limiter.succeeded(name_key)
    token = create_session(session, user)
    response = RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, token)
    return response


@router.post("/auth/server/login", response_class=HTMLResponse)
def server_login_submit(
    request: Request,
    session: DbSession,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
    server_id: Annotated[int | None, Form()] = None,
):
    """Sign in with a Jellyfin or Emby account. The credentials go to that server and are not
    stored here; what comes back is the server's word that this person has an account on it."""
    from app.clients.emby_client import EmbyAuthError, EmbyClientError
    from app.services.auth_service import (
        MediaServerSignInUnavailable, MemberSignInDisabled, sign_in_with_media_server,
    )

    from app.hardening import client_key, login_limiter, username_key, username_limiter

    key, name_key = client_key(request), username_key(username, server_id)
    login_limiter.check(key)
    username_limiter.check(name_key)
    try:
        user = sign_in_with_media_server(session, server_id, username, password)
    except EmbyAuthError:
        login_limiter.failed(key)
        username_limiter.failed(name_key)
        # The server's own message would say which was wrong; ours does not.
        return get_templates().TemplateResponse(
            request, "login.html",
            _login_context(session, next=next, error="Incorrect username or password."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except MemberSignInDisabled as exc:
        # The password was right, so this is not a failed attempt for the rate limiter.
        return get_templates().TemplateResponse(
            request, "login.html", _login_context(session, next=next, error=str(exc)),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except (EmbyClientError, MediaServerSignInUnavailable) as exc:
        return get_templates().TemplateResponse(
            request, "login.html", _login_context(session, next=next, error=str(exc)),
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    login_limiter.succeeded(key)
    username_limiter.succeeded(name_key)
    token = create_session(session, user)
    response = RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, token)
    return response


# POST only: a GET logout can be triggered by any page that embeds an image pointing here.
@router.post("/logout")
def logout(request: Request, session: DbSession):
    delete_session(session, request.cookies.get(COOKIE_NAME))
    response = RedirectResponse(_url("/login"), status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME, path=_cookie_kwargs()["path"])
    return response


@router.post("/auth/plex/start")
def plex_start(request: Request, session: DbSession):
    """Create a sign-in PIN and hand back the app.plex.tv URL for the popup."""
    from app.hardening import client_key, plex_start_limiter

    key = client_key(request)
    plex_start_limiter.check(key)
    plex_start_limiter.failed(key)     # every start counts: each one creates a PIN at plex.tv
    if not plex_sign_in_available(session):
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
    # The browser gets an opaque handle, never the PIN id: see app/auth/plex_pins.py.
    response.set_cookie(PIN_COOKIE, plex_pins.remember(pin.id),
                        max_age=plex_pins.PIN_LIFETIME_SECONDS, **_cookie_kwargs())
    return response


@router.post("/auth/plex/poll")
def plex_poll(request: Request, session: DbSession, next: Annotated[str, Form()] = ""):
    """Has the user finished signing in at plex.tv yet?"""
    handle = request.cookies.get(PIN_COOKIE)
    pin_id = plex_pins.lookup(handle)
    if pin_id is None:
        return JSONResponse(
            {"error": "This sign-in attempt expired. Please start again."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    client_id = get_or_create_client_id(session)
    try:
        token = plex_oauth.check_pin(client_id, pin_id)
    except plex_oauth.PlexOAuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_502_BAD_GATEWAY)

    if token is None:
        return JSONResponse({"status": "pending"})

    # The PIN has produced its token: spend the handle whatever happens next, so it can't be
    # replayed for a second session.
    plex_pins.forget(handle)
    try:
        user = sign_in_with_plex_token(session, token)
    except (PlexAccessDenied, MemberSignInDisabled) as exc:
        # Expected and important: a valid Plex account that isn't allowed on this install --
        # either it can't reach the server, or it can but isn't the owner and members are off.
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except plex_oauth.PlexOAuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_502_BAD_GATEWAY)

    session_token = create_session(session, user)
    response = JSONResponse({"status": "ok", "redirect": _safe_next(next or None)})
    _set_session_cookie(response, session_token)
    response.delete_cookie(PIN_COOKIE, path=_cookie_kwargs()["path"])
    return response


@router.get("/password", response_class=HTMLResponse)
def password_form(request: Request, session: DbSession, user: CurrentUser, changed: bool = False):
    """Change the local admin password.

    Only meaningful for the local account: a Plex-authenticated user's password lives at
    plex.tv and Franchisarr has never seen it.
    """
    if user is None:
        return RedirectResponse(_url("/login"), status_code=status.HTTP_303_SEE_OTHER)

    return get_templates().TemplateResponse(
        request,
        "password.html",
        {"user": user, "changed": changed, "is_local": bool(user.local_username)},
    )


@router.post("/password", response_class=HTMLResponse)
def password_change(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    current_password: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
):
    if user is None:
        return RedirectResponse(_url("/login"), status_code=status.HTTP_303_SEE_OTHER)

    from app.auth.local_admin import authenticate_local
    from app.auth.passwords import hash_password
    from app.auth.sessions import delete_sessions_for_user

    def fail(message: str):
        return get_templates().TemplateResponse(
            request,
            "password.html",
            {"user": user, "error": message, "is_local": bool(user.local_username)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not user.local_username:
        return fail("This account signs in with Plex, so there's no password here to change.")
    if authenticate_local(session, user.local_username, current_password) is None:
        return fail("That isn't your current password.")
    if len(new_password) < 8:
        return fail("Use at least 8 characters.")
    if new_password != confirm_password:
        return fail("The two new passwords don't match.")

    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()

    # Every other session belonged to whoever knew the old password. Changing it should end
    # them, which is the entire reason delete_sessions_for_user exists.
    delete_sessions_for_user(session, user.id)

    token = create_session(session, user)
    response = RedirectResponse(_url("/password?changed=1"), status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, token)
    return response

"""FastAPI dependencies for "who is asking".

`current_user` is optional and never redirects, so pages can render differently for anonymous
visitors. `require_user` / `require_admin` refuse, and are what protects a route.

Everything unauthenticated redirects to the login page rather than returning a bare 401, since
these are browser routes. The redirect is built from BASE_URL like every other link.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth.api_keys import find_user_by_api_key
from app.auth.sessions import COOKIE_NAME, get_session_user
from app.config import get_settings
from app.db import get_engine
from app.models import User


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


#: Header the CLI authenticates with. Separate from the browser session cookie so
#: `docker exec ... cli.py scan movies` needs no logged-in browser (technical challenge #21).
API_KEY_HEADER = "X-Api-Key"


def current_user(request: Request, session: DbSession) -> User | None:
    """Whoever is asking: a browser session, or an API key.

    The cookie is checked first because it is the common case; the API key is a fallback so the
    same routes serve the web UI and the CLI without duplicating them.
    """
    user = get_session_user(session, request.cookies.get(COOKIE_NAME))
    if user is not None:
        return user
    return find_user_by_api_key(session, request.headers.get(API_KEY_HEADER))


CurrentUser = Annotated[User | None, Depends(current_user)]


class LoginRequired(HTTPException):
    """Raised for an anonymous request to a protected page.

    Carries a redirect rather than a 401 body: an exception handler turns it into a redirect to
    the login form, which is what a browser should get.
    """

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")


def require_user(user: CurrentUser) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This page is only available to administrators.",
        )
    return user


RequiredUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]


def login_url(next_path: str | None = None) -> str:
    base = get_settings().base_url
    target = f"{base}/login"
    if next_path:
        from urllib.parse import quote

        target += f"?next={quote(next_path, safe='/')}"
    return target


def login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(login_url(request.url.path), status_code=status.HTTP_303_SEE_OTHER)

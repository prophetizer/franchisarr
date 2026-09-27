"""The Users page: who has an account, and ending their access. Administrators only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import AdminUser, DbSession
from app.config import get_settings
from app.services import user_service
from app.templating import get_templates

router = APIRouter()


def _page(request: Request, session, user, *, error: str | None = None, done: str | None = None,  # noqa: ANN001
          status_code: int = 200) -> HTMLResponse:
    from app.services.auth_service import members_allowed

    return get_templates().TemplateResponse(
        request, "users.html",
        {"user": user, "users": user_service.list_users(session), "error": error, "done": done,
         "members_allowed": members_allowed(session)},
        status_code=status_code,
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, session: DbSession, user: AdminUser):
    return _page(request, session, user)


@router.post("/users/{user_id}/end-sessions", response_class=HTMLResponse)
def end_sessions(request: Request, session: DbSession, user: AdminUser, user_id: int):
    user_service.end_sessions(session, user_id)
    if user_id == user.id:      # ended our own: the next request lands on the login page
        return RedirectResponse(f"{get_settings().base_url}/login", status_code=status.HTTP_303_SEE_OTHER)
    return _page(request, session, user, done="Signed out everywhere.")


@router.post("/users/{user_id}/revoke-key", response_class=HTMLResponse)
def revoke_key(request: Request, session: DbSession, user: AdminUser, user_id: int):
    user_service.revoke_key(session, user_id)
    return _page(request, session, user, done="API key revoked.")


@router.post("/users/{user_id}/remove", response_class=HTMLResponse)
def remove_user(request: Request, session: DbSession, user: AdminUser, user_id: int):
    try:
        user_service.remove(session, user_id, acting_user_id=user.id)
    except user_service.CannotRemove as exc:
        return _page(request, session, user, error=str(exc), status_code=status.HTTP_400_BAD_REQUEST)
    return _page(request, session, user, done="Account removed.")

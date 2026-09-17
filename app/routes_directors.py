"""Director pages: a director's filmography against the library."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.config import get_settings
from app.services import director_service
from app.templating import get_templates

router = APIRouter()


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


@router.get("/directors", response_class=HTMLResponse)
def directors(request: Request, session: DbSession, user: RequiredUser, sort: str = "owned"):
    sort = sort if sort in ("owned", "rating", "name") else "owned"
    views = director_service.director_views(session, user.id, sort=sort)
    return get_templates().TemplateResponse(
        request,
        "directors.html",
        {
            "user": user,
            "directors": views,
            "sort": sort,
            "floor": director_service.min_director_films(session),
            "total_missing": sum(len(v.missing) for v in views),
            "pending": sum(1 for v in views if v.pending),
        },
    )


@router.post("/directors/floor")
def set_floor(session: DbSession, user: RequiredUser, floor: Annotated[str, Form()] = "5"):
    """How many owned films a director needs before they are worth a page. Household-wide."""
    from app.services.settings_service import SettingKey, set_setting

    try:
        value = max(2, min(50, int(floor or 5)))
    except ValueError:
        value = 5
    set_setting(session, SettingKey.MIN_DIRECTOR_FILMS, str(value))
    session.commit()
    return RedirectResponse(_url("/directors"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/directors/{person_id}", response_class=HTMLResponse)
def director_detail(request: Request, session: DbSession, user: RequiredUser, person_id: int):
    view = director_service.director_view(session, person_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such director.")
    return get_templates().TemplateResponse(
        request, "director_detail.html", {"user": user, "d": view}
    )

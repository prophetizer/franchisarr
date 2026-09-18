"""Preferences: the taste settings, in one place, each with an example of what it changes.

Shown once on a fresh install, right after the libraries are chosen, and reachable from
Settings forever after. Skipping it is a valid answer -- the defaults are the cleaner lists,
and nothing they hide is thrown away.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.config import get_settings
from app.services.settings_service import SettingKey, get_setting, set_setting
from app.templating import get_templates

router = APIRouter()


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


def _flag(session, key: str) -> bool:  # noqa: ANN001
    return (get_setting(session, key) or "false").lower() == "true"


def preferences_reviewed(session) -> bool:  # noqa: ANN001
    return _flag(session, SettingKey.PREFERENCES_REVIEWED)


@router.get("/preferences", response_class=HTMLResponse)
def preferences(request: Request, session: DbSession, user: RequiredUser,
                first: bool = False, saved: bool = False):
    from app.services import director_service, movie_gap_service

    return get_templates().TemplateResponse(
        request,
        "preferences.html",
        {
            "user": user,
            "first": first,
            "saved": saved,
            "min_rating": movie_gap_service.min_gap_rating(session),
            "director_floor": director_service.min_director_films(session),
            "include_tv_films": _flag(session, SettingKey.FRANCHISE_INCLUDE_TV_FILMS),
            "include_shorts": _flag(session, SettingKey.DIRECTOR_INCLUDE_SHORTS),
        },
    )


@router.post("/preferences")
def save_preferences(
    session: DbSession,
    user: RequiredUser,
    min_rating: Annotated[str, Form()] = "0",
    director_floor: Annotated[str, Form()] = "5",
    include_tv_films: Annotated[str, Form()] = "",
    include_shorts: Annotated[str, Form()] = "",
    skip: Annotated[str, Form()] = "",
    first: Annotated[str, Form()] = "",
):
    if not skip:
        try:
            rating = max(0.0, min(10.0, float(min_rating or 0)))
        except ValueError:
            rating = 0.0
        try:
            floor = max(2, min(50, int(director_floor or 5)))
        except ValueError:
            floor = 5
        set_setting(session, SettingKey.MIN_GAP_RATING, f"{rating:g}")
        set_setting(session, SettingKey.MIN_DIRECTOR_FILMS, str(floor))
        set_setting(session, SettingKey.FRANCHISE_INCLUDE_TV_FILMS, "true" if include_tv_films else "false")
        set_setting(session, SettingKey.DIRECTOR_INCLUDE_SHORTS, "true" if include_shorts else "false")
    # Seen is seen, saved or skipped: the first-run step must never come back uninvited.
    set_setting(session, SettingKey.PREFERENCES_REVIEWED, "true")
    session.commit()
    if first:
        return RedirectResponse(_url("/"), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(_url("/preferences?saved=1"), status_code=status.HTTP_303_SEE_OTHER)

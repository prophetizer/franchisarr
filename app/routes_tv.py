"""Web UI for the TV side: spin-off suggestions, the mapping list, and heuristic candidates.

Adding a show to Sonarr is Phase 7. What this phase gives you is the list of what's missing and
the means to grow the mapping it comes from.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.clients.tmdb_client import TmdbClient
from app.models import DismissedItem, ItemType, SpinoffMapping
from app.services import tv_spinoff_service
from app.services.settings_service import SettingKey, get_setting
from app.templating import get_templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _mapping_rows(session) -> list[dict]:
    """Mappings with both ends named, since ids alone are unreadable in a list."""
    return [
        {
            "id": mapping.id,
            "source_name": tv_spinoff_service._show_name(session, mapping.source_show_tmdb_id),
            "spinoff_name": tv_spinoff_service._show_name(session, mapping.spinoff_show_tmdb_id),
        }
        for mapping in tv_spinoff_service.list_mappings(session)
    ]


def _lists(request: Request, session, user) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "partials/spinoff_lists.html",
        {"user": user, "mappings": _mapping_rows(session)},
    )


@router.get("/shows", response_class=HTMLResponse)
def shows(request: Request, session: DbSession, user: RequiredUser):
    return get_templates().TemplateResponse(
        request,
        "shows.html",
        {
            "user": user,
            "shows": tv_spinoff_service.owned_shows(session),
            "suggestions": tv_spinoff_service.missing_spinoffs(session, user.id),
            "mappings": _mapping_rows(session),
        },
    )


@router.get("/shows/candidates/close", response_class=HTMLResponse)
def close_candidates() -> HTMLResponse:
    return HTMLResponse("")


@router.get("/shows/{tmdb_id}/candidates", response_class=HTMLResponse)
def candidates(request: Request, session: DbSession, user: RequiredUser, tmdb_id: int):
    """Heuristic suggestions for one show. Computed live and never stored."""
    show = next(
        (item for item in tv_spinoff_service.owned_shows(session) if item.tmdb_id == tmdb_id),
        None,
    )
    if show is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such show.")

    api_key = get_setting(session, SettingKey.TMDB_API_KEY)
    if not api_key:
        return get_templates().TemplateResponse(
            request,
            "partials/spinoff_candidates.html",
            {
                "user": user,
                "show_name": show.title,
                "candidates": [],
                "error": "A TMDb API key is needed to search for spin-offs.",
            },
        )

    found = tv_spinoff_service.heuristic_candidates(session, TmdbClient(api_key), show)
    return get_templates().TemplateResponse(
        request,
        "partials/spinoff_candidates.html",
        {"user": user, "show_name": show.title, "candidates": found, "error": None},
    )


@router.post("/shows/mappings", response_class=HTMLResponse)
def create_mapping(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    source_show_tmdb_id: Annotated[int, Form()],
    spinoff_show_tmdb_id: Annotated[int, Form()],
):
    """Confirm a spin-off. This is the only way the curated list grows."""
    try:
        tv_spinoff_service.add_mapping(
            session,
            source_show_tmdb_id=source_show_tmdb_id,
            spinoff_show_tmdb_id=spinoff_show_tmdb_id,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Cache the show's name so the mapping list can render it without another lookup.
    api_key = get_setting(session, SettingKey.TMDB_API_KEY)
    if api_key:
        from app.clients.tmdb_client import TmdbError

        try:
            tv_spinoff_service.cache_show(
                session, TmdbClient(api_key).get_show(spinoff_show_tmdb_id)
            )
        except TmdbError:
            logger.info("Saved the mapping but couldn't cache tmdb:%s", spinoff_show_tmdb_id)

    return HTMLResponse(
        '<p role="status" class="notice-good">Saved. It will appear in your mapping list.</p>'
    )


@router.post("/shows/mappings/{mapping_id}/delete", response_class=HTMLResponse)
def delete_mapping(request: Request, session: DbSession, user: RequiredUser, mapping_id: int):
    tv_spinoff_service.remove_mapping(session, mapping_id)
    return _lists(request, session, user)


@router.post("/shows/dismiss/{tmdb_id}", response_class=HTMLResponse)
def dismiss_show(request: Request, session: DbSession, user: RequiredUser, tmdb_id: int):
    from sqlmodel import col, select

    already = session.exec(
        select(DismissedItem).where(
            col(DismissedItem.user_id) == user.id,
            col(DismissedItem.item_type) == ItemType.SHOW.value,
            col(DismissedItem.tmdb_id) == tmdb_id,
        )
    ).first()
    if already is None:
        session.add(
            DismissedItem(user_id=user.id, item_type=ItemType.SHOW.value, tmdb_id=tmdb_id)
        )
        session.commit()

    return _lists(request, session, user)

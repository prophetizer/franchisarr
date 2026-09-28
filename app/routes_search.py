"""Search: one box for everything Franchisarr knows (app/services/search_service.py).

The page and its results are the same URL. A plain request gets the whole page; htmx, asking as
the person types, gets just the results, and replaces the address so a reload or a shared link
keeps the query. Anyone signed in may search; Add stays an administrator's, as everywhere.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlmodel import col, select

from app.auth.dependencies import DbSession, RequiredUser
from app.models import DismissedItem, ItemType
from app.services import search_service
from app.templating import get_templates

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, session: DbSession, user: RequiredUser, q: str = ""):
    results = search_service.search(session, q[:200], user.id)
    partial = request.headers.get("HX-Request") == "true" and request.headers.get("HX-Target") == "search-results"
    return get_templates().TemplateResponse(
        request, "partials/search_results.html" if partial else "search.html",
        {"user": user, "results": results, "q": q[:200]},
    )


@router.post("/search/dismiss/{item_type}/{tmdb_id}", response_class=HTMLResponse)
def dismiss_from_search(request: Request, session: DbSession, user: RequiredUser, item_type: str, tmdb_id: int):
    """"Not interested", from a search result: the same per-person hide the lists use."""
    if item_type not in (ItemType.MOVIE.value, ItemType.SHOW.value):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing of that kind.")
    already = session.exec(select(DismissedItem.id).where(
        col(DismissedItem.user_id) == user.id, col(DismissedItem.item_type) == item_type,
        col(DismissedItem.tmdb_id) == tmdb_id)).first()
    if already is None:
        session.add(DismissedItem(user_id=user.id, item_type=item_type, tmdb_id=tmdb_id))
        session.commit()
    return HTMLResponse('<span class="muted">Hidden from your lists.</span>')

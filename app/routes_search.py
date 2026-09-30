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
from app.services import about_service, search_service, surprise
from app.templating import get_templates

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, session: DbSession, user: RequiredUser, q: str = ""):
    results = search_service.search(session, q[:200], user.id)
    target = request.headers.get("HX-Target") if request.headers.get("HX-Request") == "true" else None
    # Showcase's Ctrl+K box (0.51.0) wants somewhere to go, not tiles to act on.
    template = {"search-results": "partials/search_results.html",
                "quick-results": "partials/quick_results.html"}.get(target or "", "search.html")
    return get_templates().TemplateResponse(
        request, template,
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


@router.get("/about/{kind}/{tmdb_id}", response_class=HTMLResponse)
def about_title(request: Request, session: DbSession, user: RequiredUser, kind: str, tmdb_id: int):
    """The back of a flipped poster in Showcase (0.51.0): plot, genres, score, running time."""
    if kind not in (ItemType.MOVIE.value, ItemType.SHOW.value):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing of that kind.")
    found = about_service.about(session, kind, tmdb_id, about_service.tmdb_for(session))
    return get_templates().TemplateResponse(request, "partials/about.html", {"about": found})


@router.get("/surprise", response_class=HTMLResponse)
def surprise_me(request: Request, session: DbSession, user: RequiredUser, avoid: int | None = None):
    """Surprise me (0.53.0): a well-rated missing film, picked at random. `avoid` is the one just
    shown, so "spin again" always moves."""
    pick, reel = surprise.spin(session, user.id, avoid=avoid)
    found = about_service.about(session, "movie", pick.tmdb_id, about_service.tmdb_for(session)) if pick else None
    return get_templates().TemplateResponse(
        request, "partials/surprise.html", {"user": user, "pick": pick, "reel": reel, "about": found,
                          "min_rating": surprise.MIN_RATING},
    )

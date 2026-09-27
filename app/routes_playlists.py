"""Build a Plex playlist from a franchise, collection or director page. Administrators only:
it writes to the media server, in the owner's account."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import AdminUser, DbSession
from app.models import ItemType
from app.services import playlist_service
from app.services.artwork import backdrop_url, poster_url
from app.templating import get_templates

router = APIRouter()


def _art(backdrop_path: str | None, titles) -> playlist_service.PosterArt:  # noqa: ANN001
    """The poster's artwork: the page's backdrop, and film posters oldest first as a fallback."""
    dated = sorted((t for t in titles if getattr(t, "poster_path", None)),
                   key=lambda t: str(getattr(t, "release_date", None) or getattr(t, "year", None)
                                     or getattr(t, "release_year", None) or "9999"))
    return playlist_service.PosterArt(
        backdrop_url=backdrop_url(backdrop_path, "w1280") if backdrop_path else None,
        poster_urls=tuple(poster_url(t.poster_path, "w342") for t in dated[:9]),
    )


def _render(request: Request, result: playlist_service.PlaylistResult) -> HTMLResponse:
    return get_templates().TemplateResponse(request, "partials/playlist_result.html", {"r": result})


@router.post("/franchises/{wikidata_id}/playlist", response_class=HTMLResponse)
def franchise_playlist(request: Request, session: DbSession, user: AdminUser, wikidata_id: str):
    from app.services import franchise_service

    view = franchise_service.franchise_view(session, wikidata_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such franchise.")
    refs = [(t.item_type, t.tmdb_id) for t in view.owned_films + view.owned_shows]
    art = _art(view.backdrop_path, view.owned_films)
    return _render(request, playlist_service.build(session, view.name, refs, art))


@router.post("/collections/{collection_id}/playlist", response_class=HTMLResponse)
def collection_playlist(request: Request, session: DbSession, user: AdminUser, collection_id: int):
    from app.services import movie_gap_service

    gap = next((g for g in movie_gap_service.collection_gaps(session, user.id, only={collection_id})
                if g.collection_id == collection_id), None)
    if gap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such collection.")
    refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in gap.owned]
    art = _art(getattr(gap, "backdrop_path", None), gap.owned)
    return _render(request, playlist_service.build(session, gap.name, refs, art))


@router.post("/directors/{person_id}/playlist", response_class=HTMLResponse)
def director_playlist(request: Request, session: DbSession, user: AdminUser, person_id: int):
    from app.services import director_service

    view = director_service.director_view(session, person_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such director.")
    refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in view.owned]
    art = _art(None, view.owned)       # a person has no backdrop: the film mosaic
    return _render(request, playlist_service.build(session, view.name, refs, art))

"""Build a Plex playlist from a franchise, collection or director page. Administrators only:
it writes to the media server, in the owner's account."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import AdminUser, DbSession
from app.models import ItemType
from app.services import playlist_service
from app.templating import get_templates

router = APIRouter()


def _render(request: Request, result: playlist_service.PlaylistResult) -> HTMLResponse:
    return get_templates().TemplateResponse(request, "partials/playlist_result.html", {"r": result})


@router.post("/franchises/{wikidata_id}/playlist", response_class=HTMLResponse)
def franchise_playlist(request: Request, session: DbSession, user: AdminUser, wikidata_id: str):
    from app.services import franchise_service

    view = franchise_service.franchise_view(session, wikidata_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such franchise.")
    refs = [(t.item_type, t.tmdb_id) for t in view.owned_films + view.owned_shows]
    art = playlist_service.art_from(view.backdrop_path, view.owned_films)
    return _render(request, playlist_service.build(session, view.name, refs, art))


@router.post("/collections/{collection_id}/playlist", response_class=HTMLResponse)
def collection_playlist(request: Request, session: DbSession, user: AdminUser, collection_id: int):
    from app.services import movie_gap_service

    gap = next((g for g in movie_gap_service.collection_gaps(session, user.id, only={collection_id})
                if g.collection_id == collection_id), None)
    if gap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such collection.")
    refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in gap.owned]
    art = playlist_service.art_from(getattr(gap, "backdrop_path", None), gap.owned)
    return _render(request, playlist_service.build(session, gap.name, refs, art))


@router.post("/directors/{person_id}/playlist", response_class=HTMLResponse)
def director_playlist(request: Request, session: DbSession, user: AdminUser, person_id: int):
    from app.services import director_service

    view = director_service.director_view(session, person_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such director.")
    refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in view.owned]
    art = playlist_service.art_from(None, view.owned)   # a person has no backdrop: their films
    return _render(request, playlist_service.build(session, view.name, refs, art))

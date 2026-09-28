"""Build a playlist from a franchise, collection or director page -- on every server or on
one -- and delete Franchisarr's playlists from the Servers page. Administrators only: both write
to the media server, in the owner's account."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import AdminUser, DbSession
from app.models import ItemType
from app.services import playlist_service
from app.templating import get_templates

router = APIRouter()


def _render(request: Request, result: playlist_service.PlaylistResult) -> HTMLResponse:
    return get_templates().TemplateResponse(request, "partials/playlist_result.html", {"r": result})


def _server_id(session, raw: str) -> int | None:  # noqa: ANN001
    """`server` from a button: "" or "all" means every server; otherwise the id of a server a
    playlist can go on, or a 404 rather than a silent build everywhere."""
    raw = raw.strip()
    if raw in ("", "all"):
        return None
    if raw.isdigit() and any(s.id == int(raw) for s in playlist_service.targets(session)):
        return int(raw)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such server, or it's turned off.")


Server = Annotated[str, Form()]


@router.post("/franchises/{wikidata_id}/playlist", response_class=HTMLResponse)
def franchise_playlist(request: Request, session: DbSession, user: AdminUser, wikidata_id: str,
                       server: Server = ""):
    from app.services import franchise_service

    view = franchise_service.franchise_view(session, wikidata_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such franchise.")
    refs = [(t.item_type, t.tmdb_id) for t in view.owned_films + view.owned_shows]
    art = playlist_service.art_from(view.backdrop_path, view.owned_films)
    return _render(request, playlist_service.build(session, view.name, refs, art,
                                                   server_id=_server_id(session, server)))


@router.post("/collections/{collection_id}/playlist", response_class=HTMLResponse)
def collection_playlist(request: Request, session: DbSession, user: AdminUser, collection_id: int,
                        server: Server = ""):
    from app.services import movie_gap_service

    gap = next((g for g in movie_gap_service.collection_gaps(session, user.id, only={collection_id})
                if g.collection_id == collection_id), None)
    if gap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such collection.")
    refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in gap.owned]
    art = playlist_service.art_from(getattr(gap, "backdrop_path", None), gap.owned)
    return _render(request, playlist_service.build(session, gap.name, refs, art,
                                                   server_id=_server_id(session, server)))


@router.post("/directors/{person_id}/playlist", response_class=HTMLResponse)
def director_playlist(request: Request, session: DbSession, user: AdminUser, person_id: int,
                      server: Server = ""):
    from app.services import director_service

    view = director_service.director_view(session, person_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such director.")
    refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in view.owned]
    art = playlist_service.art_from(None, view.owned)   # a person has no backdrop: their films
    return _render(request, playlist_service.build(session, view.name, refs, art,
                                                   server_id=_server_id(session, server)))


# ---------------------------------------------------------------------- deleting ours


@router.get("/playlists/delete", response_class=HTMLResponse)
def confirm_delete(request: Request, session: DbSession, user: AdminUser,
                   server: Annotated[str, Query()] = "all"):
    """The warning before anything is deleted: exactly which playlists would go, from where,
    and a button that says how many. Nothing is deleted by this request."""
    server_id = _server_id(session, server)
    found = playlist_service.ours(session, server_id)
    return get_templates().TemplateResponse(request, "partials/playlist_delete.html", {
        "confirm": True, "found": found, "server": "all" if server_id is None else str(server_id),
        "total": sum(len(f.titles) for f in found),
    })


@router.post("/playlists/delete", response_class=HTMLResponse)
def delete_playlists(request: Request, session: DbSession, user: AdminUser, server: Server = "all"):
    done = playlist_service.delete_ours(session, _server_id(session, server))
    return get_templates().TemplateResponse(request, "partials/playlist_delete.html", {
        "confirm": False, "found": done, "total": sum(len(d.titles) for d in done),
    })

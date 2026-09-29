"""Build a playlist from a franchise, collection or director page -- on every server or on
one -- and delete Franchisarr's playlists from the Servers page. Administrators only: both write
to the media server, in the owner's account."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlmodel import select

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


# ---------------------------------------------------------------------- bulk actions
#
# The Servers page's "Bulk actions": add playlists for every franchise/collection/director,
# delete Franchisarr's, or delete every playlist in the account Franchisarr uses -- each on one
# server or all of them. Deleting always shows what would go first; deleting *every* playlist
# (people's own included) also needs DELETE typed, checked here and not only in the page.


def _where(session, server_id: int | None) -> str:  # noqa: ANN001
    if server_id is None:
        return "every server"
    from app.models import MediaServer

    return session.get(MediaServer, server_id).name


def _scope(raw: str) -> bool:
    """True for "every playlist", False for Franchisarr's only."""
    if raw not in ("ours", "all"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such scope.")
    return raw == "all"


@router.get("/playlists/delete", response_class=HTMLResponse)
def confirm_delete(request: Request, session: DbSession, user: AdminUser,
                   server: Annotated[str, Query()] = "all", scope: Annotated[str, Query()] = "ours"):
    """The warning before anything is deleted: exactly which playlists would go, from where,
    and a button that says how many. Nothing is deleted by this request."""
    everything = _scope(scope)
    server_id = _server_id(session, server)
    found = playlist_service.ours(session, server_id, everything=everything)
    return _delete_panel(request, session, found, server_id, everything, confirm=True)


def _delete_panel(request, session, found, server_id, everything, *, confirm, error=None):  # noqa: ANN001, ANN202
    from app.models import MediaServer

    kinds = dict(session.exec(select(MediaServer.name, MediaServer.kind)).all())
    return get_templates().TemplateResponse(request, "partials/playlist_delete.html", {
        "confirm": confirm, "found": found, "total": sum(len(f.titles) for f in found),
        "server": "all" if server_id is None else str(server_id), "scope": "all" if everything else "ours",
        "everything": everything, "error": error,
        # Jellyfin/Emby can't say who owns a playlist, so shared ones may be listed (0.37.0).
        "shared_caveat": everything and any(kinds.get(f.server) != "plex" for f in found if f.titles),
    })


@router.post("/playlists/delete", response_class=HTMLResponse)
def delete_playlists(request: Request, session: DbSession, user: AdminUser, server: Server = "all",
                     scope: Annotated[str, Form()] = "ours", confirm: Annotated[str, Form()] = ""):
    everything = _scope(scope)
    server_id = _server_id(session, server)
    if everything and confirm.strip() != "DELETE":
        # The page won't enable the button without it; this is for anything else that posts.
        found = playlist_service.ours(session, server_id, everything=True)
        return _delete_panel(request, session, found, server_id, True, confirm=True,
                             error="Type DELETE to confirm.")
    done = playlist_service.delete_ours(session, server_id, everything=everything)
    return _delete_panel(request, session, done, server_id, everything, confirm=False)


@router.get("/playlists/add-all", response_class=HTMLResponse)
def add_all_form(request: Request, session: DbSession, user: AdminUser, server: Annotated[str, Query()] = "all"):
    from app.services import playlist_bulk

    server_id = _server_id(session, server)
    return get_templates().TemplateResponse(request, "partials/playlist_bulk.html", {
        "form": True, "counts": playlist_bulk.counts(session), "bulk": playlist_bulk.current(),
        "server": "all" if server_id is None else str(server_id), "where": _where(session, server_id),
    })


@router.post("/playlists/add-all", response_class=HTMLResponse)
def add_all(request: Request, session: DbSession, user: AdminUser, server: Server = "all",
            kinds: Annotated[list[str], Form()] = []):  # noqa: B006 - FastAPI reads the default
    from app.services import playlist_bulk

    chosen = [k for k in kinds if k in playlist_bulk.KINDS]
    server_id = _server_id(session, server)
    if not chosen:
        return get_templates().TemplateResponse(request, "partials/playlist_bulk.html", {
            "form": True, "counts": playlist_bulk.counts(session), "bulk": playlist_bulk.current(),
            "server": server, "where": _where(session, server_id), "error": "Pick at least one kind.",
        })
    playlist_bulk.run_in_background(chosen, server_id, _where(session, server_id))
    return _bulk_status(request)


def _bulk_status(request: Request) -> HTMLResponse:
    from app.services import playlist_bulk

    return get_templates().TemplateResponse(request, "partials/playlist_bulk.html",
                                            {"form": False, "bulk": playlist_bulk.current()})


@router.get("/playlists/add-all/status", response_class=HTMLResponse)
def add_all_status(request: Request, user: AdminUser):
    return _bulk_status(request)


@router.post("/playlists/add-all/stop", response_class=HTMLResponse)
def add_all_stop(request: Request, user: AdminUser):
    from app.services import playlist_bulk

    playlist_bulk.stop()
    return _bulk_status(request)


# ---------------------------------------------------------------------- playlist sync


@router.get("/playlists", response_class=HTMLResponse)
def playlists_page(request: Request, session: DbSession, user: AdminUser, error: str | None = None):
    from app.services import media_server_service, playlist_sync

    return get_templates().TemplateResponse(request, "playlists.html", {
        "user": user, "servers": playlist_sync.page(session), "sync": playlist_sync.current(),
        "several": len(media_server_service.enabled_servers(session)) > 1, "error": error,
        "sync_all": playlist_sync.sync_all(session), "keep_franchisarr": playlist_sync.keep_franchisarr(session),
    })


@router.post("/playlists/switches")
def sync_switches(session: DbSession, user: AdminUser, every: Annotated[str, Form()] = "",
                  franchisarr: Annotated[str, Form()] = ""):
    from app.services import playlist_sync

    playlist_sync.set_switches(session, every=bool(every), franchisarr=bool(franchisarr))
    return _back_to_playlists()


@router.post("/playlists/sync/exclude")
def sync_exclude(session: DbSession, user: AdminUser, server_id: Annotated[int, Form()],
                 playlist_id: Annotated[str, Form()], title: Annotated[str, Form()] = ""):
    from app.services import playlist_sync

    if not any(s.id == server_id for s in playlist_service.targets(session)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such server, or it's turned off.")
    playlist_sync.exclude(session, server_id, playlist_id.strip(), title.strip()[:300] or playlist_id)
    return _back_to_playlists()


def _back_to_playlists(error: str | None = None):  # noqa: ANN202
    from urllib.parse import quote

    from fastapi.responses import RedirectResponse

    from app.config import get_settings

    target = f"{get_settings().base_url}/playlists" + (f"?error={quote(error)}" if error else "")
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/playlists/sync/on")
def sync_on(session: DbSession, user: AdminUser, server_id: Annotated[int, Form()],
            playlist_id: Annotated[str, Form()], title: Annotated[str, Form()] = ""):
    from app.services import playlist_sync

    if not any(s.id == server_id for s in playlist_service.targets(session)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such server, or it's turned off.")
    try:
        playlist_sync.enable(session, server_id, playlist_id.strip(), title.strip()[:300] or playlist_id)
    except ValueError as exc:
        return _back_to_playlists(str(exc))
    return _back_to_playlists()


@router.post("/playlists/sync/{sync_id}/off")
def sync_off(session: DbSession, user: AdminUser, sync_id: int):
    from app.services import playlist_sync

    playlist_sync.disable(session, sync_id)
    return _back_to_playlists()


def _sync_status(request: Request, user) -> HTMLResponse:  # noqa: ANN001
    from app.services import playlist_sync

    return get_templates().TemplateResponse(request, "partials/sync_status.html",
                                            {"user": user, "sync": playlist_sync.current()})


@router.post("/playlists/sync/run", response_class=HTMLResponse)
def sync_now(request: Request, user: AdminUser):
    from app.services import playlist_sync

    playlist_sync.run_in_background("manual")
    return _sync_status(request, user)


@router.get("/playlists/sync/status", response_class=HTMLResponse)
def sync_status(request: Request, user: AdminUser):
    return _sync_status(request, user)

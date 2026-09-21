"""Import lists: what Franchisarr finds, as JSON the *arrs can poll.

The *arr community does not click Add per film. Radarr and Sonarr both have "Custom List"
import lists -- a URL returning a JSON array of ids that the app polls on a schedule and applies
its own rules to: monitor or not, which root folder, which quality profile, search on add.
Exposing the gap lists in that shape means a user can say "Radarr, take everything Franchisarr
finds above 7.0" and never open this app again.

This keeps the promise that nothing auto-adds. Franchisarr still sends nothing to anyone; the
user opts in inside Radarr, with Radarr's own switches, which is the explicit act.

The key rides in the query string, because neither *arr can send a header to a list URL. That
puts it in their logs, as their own list URLs' keys are. The endpoints are read-only and the key
is the same per-user credential the CLI uses, revocable by generating a new one.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.auth.api_keys import find_user_by_api_key
from app.config import get_settings
from app.auth.dependencies import API_KEY_HEADER, DbSession
from app.models import ItemType, TmdbShow, User
from app.services import (
    cross_media_service,
    director_service,
    franchise_service,
    movie_gap_service,
    tv_spinoff_service,
    upcoming_service,
)

router = APIRouter(prefix="/api/lists")

LIST_NAMES = ("collections", "upcoming", "directors", "franchises", "films", "shows")

#: Shows looked up on TMDb during one poll of the shows list, to keep the response quick.
LOOKUPS_PER_REQUEST = 50


def _tmdb(session: Session):
    from app.clients.tmdb_client import TmdbClient
    from app.services.settings_service import SettingKey, get_setting

    key = get_setting(session, SettingKey.TMDB_API_KEY)
    return TmdbClient(key) if key else None


def list_user(request: Request, session: DbSession, api_key: str | None = Query(default=None)) -> User:
    """A key from the query string, or the usual header. No cookie: a list URL is for a machine."""
    user = find_user_by_api_key(session, api_key or request.headers.get(API_KEY_HEADER))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A valid api_key is required.")
    return user


def _film(tmdb_id: int, title: str, year: int | None, *, source: str, detail: str = "") -> dict:
    # tmdbId is what Radarr's Custom List parser reads; the rest is for a human looking at the
    # URL in a browser to check what their list would do.
    return {"tmdbId": tmdb_id, "title": title, "year": year, "source": source, "detail": detail}


def _films_from_collections(session: Session, user: User, *, min_rating: float | None,
                            upcoming: bool) -> list[dict]:
    out = []
    for gap in movie_gap_service.collection_gaps(session, user.id):
        # missing + hidden, then this list's own floor: the page has already folded films below
        # the household floor into `hidden`, and a URL asking for min_rating=0 means all of them.
        pool = list(gap.missing) + list(gap.hidden) + (list(gap.upcoming) if upcoming else [])
        for m in pool:
            if min_rating is not None and m.falls_below(min_rating):
                continue
            out.append(_film(m.tmdb_id, m.title, m.release_year, source="collection", detail=gap.name))
    return out


def _films_from_directors(session: Session, user: User, *, min_rating: float | None) -> list[dict]:
    out = []
    for view in director_service.director_views(session, user.id):
        for m in list(view.missing) + list(view.hidden):
            if min_rating is not None and m.falls_below(min_rating):
                continue
            out.append(_film(m.tmdb_id, m.title, m.year, source="director", detail=view.name))
    return out


def _films_from_franchises(session: Session, user: User) -> list[dict]:
    out = []
    for view in franchise_service.franchise_views(session, user.id):
        for t in view.missing_films:
            out.append(_film(t.tmdb_id, t.title, t.year, source="franchise", detail=view.name))
    return out


def _films_upcoming(session: Session, user: User) -> list[dict]:
    return [
        _film(f.tmdb_id, f.title, f.release.year if f.release else None, source="upcoming",
              detail=f"{f.collection_name} · {f.release_date or 'no date yet'}")
        for f in upcoming_service.upcoming_films(session, user.id)
    ]


def _dedupe(items: list[dict], key: str) -> list[dict]:
    seen: set[int] = set()
    out = []
    for item in items:
        if item[key] in seen:
            continue
        seen.add(item[key])
        out.append(item)
    return out


def _shows(session: Session, user: User) -> tuple[list[dict], int]:
    """Sonarr's Custom List parser reads tvdbId. Shows TMDb holds no TVDB id for are left out,
    with a count in the response headers so the omission is visible rather than silent."""
    candidates: list[tuple[int, str, int | None, str, str]] = []
    for s in tv_spinoff_service.missing_spinoffs(session, user.id):
        candidates.append((s.spinoff_tmdb_id, s.spinoff_name, s.first_air_year, "spin-off", s.relationships))
    for s in cross_media_service.suggestions(session, ItemType.SHOW.value, user.id):
        candidates.append((s.target_tmdb_id, s.target_title, s.target_year, "continuation", s.relationships))
    for view in franchise_service.franchise_views(session, user.id):
        for t in view.missing_shows:
            candidates.append((t.tmdb_id, t.title, t.year, "franchise", view.name))

    tmdb = _tmdb(session)
    lookups = 0
    out, seen, without_tvdb = [], set(), 0
    for tmdb_id, title, year, source, detail in candidates:
        if tmdb_id in seen:
            continue
        seen.add(tmdb_id)
        cached = session.get(TmdbShow, tmdb_id)
        if cached is None and tmdb is not None and lookups < LOOKUPS_PER_REQUEST:
            # A show reached through a franchise roster before the cache learned it. Fetched
            # here, once, and cached -- bounded per request so a poll never runs long; the rest
            # are picked up next time round.
            lookups += 1
            try:
                cached = tv_spinoff_service.cache_show(session, tmdb.get_show(tmdb_id))
            except Exception:  # noqa: BLE001 - a list must not fail on one show
                cached = None
        if cached is None or not cached.tvdb_id:
            without_tvdb += 1
            continue
        out.append({"tvdbId": cached.tvdb_id, "tmdbId": tmdb_id, "title": title, "year": year,
                    "source": source, "detail": detail})
    return out, without_tvdb


@router.get("/upcoming.ics")
def upcoming_calendar(request: Request, session: DbSession, user: User = Depends(list_user)):
    """The Upcoming page as a calendar subscription: one all-day event per dated film.

    Same key as the import lists, same reasoning for it being in the URL -- a calendar app can't
    send a header either. Undated films are omitted; they appear once TMDb gives them a date.
    """
    from fastapi.responses import Response

    from app.services import ical

    films = upcoming_service.upcoming_films(session, user.id)
    # Links back to the collection page use the address the request arrived on, which behind a
    # reverse proxy is the public one only if the proxy forwards it; a wrong link is a nuisance,
    # not a fault, so this is best effort.
    link_base = str(request.base_url).rstrip("/") + get_settings().base_url + "/collections"
    body = ical.calendar(films, domain=request.url.hostname or "franchisarr", link_base=link_base)
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "no-cache",
                             "Content-Disposition": 'inline; filename="franchisarr-upcoming.ics"'})


@router.get("/{name}.json")
def import_list(
    name: str,
    session: DbSession,
    user: User = Depends(list_user),
    min_rating: float | None = Query(default=None, ge=0, le=10),
    include_upcoming: bool = Query(default=False),
):
    """One of: collections, upcoming, directors, franchises, films (every film list at once),
    shows. `min_rating` overrides the household rating floor for this list only."""
    if name not in LIST_NAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No list called {name!r}.")

    # The household floor applies unless the URL says otherwise -- so a list built with
    # min_rating=0 shows everything even if the page hides some of it.
    floor = movie_gap_service.min_gap_rating(session) if min_rating is None else min_rating
    floor = floor or None

    headers = {"Cache-Control": "no-cache", "X-Franchisarr-List": name}
    if name == "shows":
        items, omitted = _shows(session, user)
        headers["X-Franchisarr-Omitted-Without-TVDB-Id"] = str(omitted)
        return JSONResponse(items, headers=headers)

    if name == "collections":
        items = _films_from_collections(session, user, min_rating=floor, upcoming=include_upcoming)
    elif name == "upcoming":
        items = _films_upcoming(session, user)
    elif name == "directors":
        items = _films_from_directors(session, user, min_rating=floor)
    elif name == "franchises":
        items = _films_from_franchises(session, user)
    else:  # films: everything, once each
        items = (_films_from_collections(session, user, min_rating=floor, upcoming=include_upcoming)
                 + _films_from_directors(session, user, min_rating=floor)
                 + _films_from_franchises(session, user)
                 + [_film(s.target_tmdb_id, s.target_title, s.target_year, source="continuation",
                          detail=s.relationships)
                    for s in cross_media_service.suggestions(session, ItemType.MOVIE.value, user.id)])
    return JSONResponse(_dedupe(items, "tmdbId"), headers=headers)

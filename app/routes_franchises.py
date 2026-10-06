"""Franchise pages: one per franchise, across both media."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.services import about_service, end_credits, franchise_map, franchise_service, franchisarr_playlists, playlist_service, timeline
from app.templating import get_templates

router = APIRouter()


def _multi_server(session) -> bool:  # noqa: ANN001 - a Session
    """Naming the server a title sits on only tells the reader something when there are two."""
    from app.services import media_server_service

    return len(media_server_service.list_servers(session)) > 1


@router.get("/franchises", response_class=HTMLResponse)
def franchises(request: Request, session: DbSession, user: RequiredUser, sort: str | None = None,
               dir: str | None = None):  # noqa: A002
    from app.config import get_settings
    from app.services import az, sorting

    current = sorting.resolve(session, user.id, "franchises", sort, dir)
    every = franchise_service.franchise_views(session, user.id)
    views = sorting.sort_groups(every, "franchises", current)
    base = get_settings().base_url
    return get_templates().TemplateResponse(
        request,
        "franchises.html",
        {
            "user": user,
            "franchises": views,
            "az_rail": az.rail(sorting.sort_groups(every, "franchises", ("name", "asc")), path=f"{base}/franchises",
                               size=max(1, len(every))),
            "az_ids": az.anchors(views, current),
            "sort_ctl": sorting.control("franchises", current, f"{base}/franchises"),
            "total_missing": sum(v.missing for v in views),
            "both": sum(1 for v in views if v.spans_both),
        },
    )


@router.get("/franchises/{wikidata_id}", response_class=HTMLResponse)
def franchise_detail(request: Request, session: DbSession, user: RequiredUser, wikidata_id: str,
                     sort: str | None = None, dir: str | None = None):  # noqa: A002
    from app.config import get_settings
    from app.services import sorting

    detail_sort = sorting.resolve(session, user.id, "detail", sort, dir)
    if detail_sort[0] == "rating":
        # Franchise titles carry no rating (they come from Wikidata and TMDb collections alike),
        # so "rating" isn't offered here; a remembered one reads as release order.
        detail_sort = sorting.default("detail")
    view = franchise_service.franchise_view(session, wikidata_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such franchise.")
    steps = timeline.build(view.owned_films + view.owned_shows, view.missing_films + view.missing_shows,
                           view.upcoming_films)
    mood = about_service.mood(session, film_ids=[t.tmdb_id for t in view.owned_films + view.missing_films])
    return get_templates().TemplateResponse(
        request, "franchise_detail.html",
        {"user": user, "f": view, "multi_server": _multi_server(session),
         "can_playlist": playlist_service.available(session) and view.owned > 0,
         "playlist_servers": playlist_service.targets(session),
         "playlist_kept": franchisarr_playlists.kept_on(session, "franchises", wikidata_id),
         "timeline": steps,
         "horror": mood == "horror", "mood": mood,
         "credits": end_credits.for_page(session, user, steps),
         "franchise_map": franchise_map.build(session, view),
         "map_shape": franchise_map.shape_of(session, user.id),
         "detail_sort": detail_sort,
         "sort_ctl": sorting.control(
             "detail", detail_sort, f"{get_settings().base_url}/franchises/{wikidata_id}",
             exclude=("rating",))}
    )

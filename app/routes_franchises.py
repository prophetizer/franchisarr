"""Franchise pages: one per franchise, across both media."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.services import franchise_service, playlist_service
from app.templating import get_templates

router = APIRouter()


def _multi_server(session) -> bool:  # noqa: ANN001 - a Session
    """Naming the server a title sits on only tells the reader something when there are two."""
    from app.services import media_server_service

    return len(media_server_service.list_servers(session)) > 1


@router.get("/franchises", response_class=HTMLResponse)
def franchises(request: Request, session: DbSession, user: RequiredUser, sort: str | None = None):
    from app.config import get_settings
    from app.services import sorting

    sort = sorting.resolve(session, user.id, "franchises", sort)
    views = sorting.sort_groups(franchise_service.franchise_views(session, user.id), "franchises", sort)
    base = get_settings().base_url
    return get_templates().TemplateResponse(
        request,
        "franchises.html",
        {
            "user": user,
            "franchises": views,
            "sort_links": sorting.links("franchises", sort, lambda key: f"{base}/franchises?sort={key}"),
            "total_missing": sum(v.missing for v in views),
            "both": sum(1 for v in views if v.spans_both),
        },
    )


@router.get("/franchises/{wikidata_id}", response_class=HTMLResponse)
def franchise_detail(request: Request, session: DbSession, user: RequiredUser, wikidata_id: str,
                     sort: str | None = None):
    from app.config import get_settings
    from app.services import sorting

    detail_sort = sorting.resolve(session, user.id, "detail", sort)
    if detail_sort == "rating":
        # Franchise titles carry no rating (they come from Wikidata and TMDb collections alike),
        # so "rating" isn't offered here; a remembered one reads as release order.
        detail_sort = "release"
    view = franchise_service.franchise_view(session, wikidata_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such franchise.")
    return get_templates().TemplateResponse(
        request, "franchise_detail.html",
        {"user": user, "f": view, "multi_server": _multi_server(session),
         "can_playlist": playlist_service.available(session) and view.owned > 0,
         "detail_sort": detail_sort,
         "sort_links": sorting.links(
             "detail", detail_sort,
             lambda key: f"{get_settings().base_url}/franchises/{wikidata_id}?sort={key}",
             exclude=("rating",))}
    )

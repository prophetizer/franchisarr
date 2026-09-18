"""Franchise pages: one per franchise, across both media."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.services import franchise_service
from app.templating import get_templates

router = APIRouter()


def _multi_server(session) -> bool:  # noqa: ANN001 - a Session
    """Naming the server a title sits on only tells the reader something when there are two."""
    from app.services import media_server_service

    return len(media_server_service.list_servers(session)) > 1


@router.get("/franchises", response_class=HTMLResponse)
def franchises(request: Request, session: DbSession, user: RequiredUser):
    views = franchise_service.franchise_views(session, user.id)
    return get_templates().TemplateResponse(
        request,
        "franchises.html",
        {
            "user": user,
            "franchises": views,
            "total_missing": sum(v.missing for v in views),
            "both": sum(1 for v in views if v.spans_both),
        },
    )


@router.get("/franchises/{wikidata_id}", response_class=HTMLResponse)
def franchise_detail(request: Request, session: DbSession, user: RequiredUser, wikidata_id: str):
    view = franchise_service.franchise_view(session, wikidata_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such franchise.")
    return get_templates().TemplateResponse(
        request, "franchise_detail.html", {"user": user, "f": view, "multi_server": _multi_server(session)}
    )

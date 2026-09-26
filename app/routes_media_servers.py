"""Managing Plex, Jellyfin and Emby servers from the UI.

Mirrors the Radarr/Sonarr instance page: credentials are write-only (docs/DEVELOPMENT.md
convention 3) -- the list shows a mask, and changing one means entering it again. Editing a server
with the credential field left blank keeps the stored one.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import AdminUser, DbSession
from app.clients.media_server import MediaServerError, MediaServerKind
from app.config import get_settings
from app.logging_config import mask_secret
from app.services import media_server_service
from app.templating import get_templates

logger = logging.getLogger(__name__)

router = APIRouter()

KINDS = [(kind.value, media_server_service.LABELS[kind]) for kind in MediaServerKind]


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


def _view(server) -> dict:
    return {
        "id": server.id,
        "name": server.name,
        "kind": server.kind,
        "label": media_server_service.label(server.kind),
        "url": server.url,
        "enabled": server.enabled,
        "watched_user": server.watched_user,
        "masked_credential": mask_secret(server.credential),
        "identity_known": bool(server.machine_identifier),
    }


def _get(session, server_id: int):
    server = media_server_service.get_server(session, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such media server.")
    return server


@router.get("/media-servers", response_class=HTMLResponse)
def media_servers_page(
    request: Request, session: DbSession, user: AdminUser, saved: bool = False,
    error: str | None = None,
):
    return get_templates().TemplateResponse(
        request,
        "media_servers.html",
        {
            "user": user,
            "servers": [_view(s) for s in media_server_service.list_servers(session)],
            "kinds": KINDS,
            "saved": saved,
            "error": error,
        },
    )


def _clean(name: str, url: str, kind: str) -> tuple[str, str, str]:
    try:
        kind = MediaServerKind(kind.strip().lower()).value
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown server type.")
    name, url = name.strip(), url.strip().rstrip("/")
    if not name or not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="A server needs a name and a URL.")
    return name, url, kind


@router.post("/media-servers", response_class=HTMLResponse)
def add_server(
    request: Request,
    session: DbSession,
    user: AdminUser,
    name: Annotated[str, Form()],
    kind: Annotated[str, Form()],
    url: Annotated[str, Form()],
    credential: Annotated[str, Form()],
    watched_user: Annotated[str, Form()] = "",
):
    name, url, kind = _clean(name, url, kind)
    if not credential.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="A new server needs its token or API key.")
    if any(s.name == name for s in media_server_service.list_servers(session)):
        return RedirectResponse(_url("/media-servers?error=A+server+with+that+name+already+exists."),
                                status_code=status.HTTP_303_SEE_OTHER)
    media_server_service.create_server(
        session, name=name, kind=kind, url=url, credential=credential.strip(),
        watched_user=watched_user.strip() or None,
    )
    return RedirectResponse(_url("/media-servers?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/media-servers/{server_id}", response_class=HTMLResponse)
def edit_server(
    request: Request,
    session: DbSession,
    user: AdminUser,
    server_id: int,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    credential: Annotated[str, Form()] = "",
    watched_user: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
):
    server = _get(session, server_id)
    name, url, _ = _clean(name, url, server.kind)
    if any(s.name == name and s.id != server.id for s in media_server_service.list_servers(session)):
        return RedirectResponse(_url("/media-servers?error=A+server+with+that+name+already+exists."),
                                status_code=status.HTTP_303_SEE_OTHER)
    if url != server.url:
        # A different address may be a different server; the sign-in check must relearn it.
        server.machine_identifier = None
    media_server_service.update_server(
        session, server, name=name, url=url, credential=credential.strip(),
        watched_user=watched_user.strip() or None, enabled=bool(enabled),
    )
    return RedirectResponse(_url("/media-servers?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/media-servers/{server_id}/delete", response_class=HTMLResponse)
def remove_server(session: DbSession, user: AdminUser, server_id: int):
    media_server_service.delete_server(session, server_id)
    return RedirectResponse(_url("/media-servers?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/media-servers/{server_id}/test", response_class=HTMLResponse)
def test_server(request: Request, session: DbSession, user: AdminUser, server_id: int):
    server = _get(session, server_id)
    context: dict = {"user": user, "ok": False, "version": "", "error": ""}
    try:
        client = media_server_service.client_for(server)
        context.update(ok=True, version=client.test_connection())
        if server.kind == MediaServerKind.PLEX.value:
            # Reaching it is the moment to learn its identity, which is what Plex sign-in needs.
            from app.services.auth_service import discover_machine_identifier

            discover_machine_identifier(session, server, client)
    except MediaServerError as exc:
        context["error"] = str(exc)
    return get_templates().TemplateResponse(request, "partials/instance_test.html", context)

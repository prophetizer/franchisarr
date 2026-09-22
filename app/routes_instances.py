"""Managing Radarr, Sonarr and Overseerr/Jellyseerr instances from the UI.

API keys are write-only here (docs/DEVELOPMENT.md convention 3): the list shows a mask, and changing a key
means entering it again rather than editing a pre-filled field. A masked value that round-trips
through a form is not masked -- it is just hidden from the person looking at the screen while
sitting in the page source.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import AdminUser, DbSession, RequiredUser
from app.clients.radarr_client import RadarrError
from app.clients.seerr_client import SeerrError
from app.clients.sonarr_client import SonarrError
from app.config import get_settings
from app.logging_config import mask_secret
from app.services import instance_service, seerr_instance_service, sonarr_instance_service
from app.templating import get_templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


def _view(instance) -> dict:
    """A row for the template. The key never leaves as anything but a mask."""
    return {
        "id": instance.id,
        "name": instance.name,
        "url": instance.url,
        "is_default": instance.is_default,
        "masked_key": mask_secret(instance.api_key),
        "kind": getattr(instance, "kind", None),
    }


def _service(kind: str):
    if kind == "radarr":
        return instance_service
    if kind == "sonarr":
        return sonarr_instance_service
    if kind == "seerr":
        return seerr_instance_service
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown instance type.")


@router.get("/instances", response_class=HTMLResponse)
def instances_page(
    request: Request, session: DbSession, user: RequiredUser, saved: bool = False
):
    return get_templates().TemplateResponse(
        request,
        "instances.html",
        {
            "user": user,
            "radarr": [_view(i) for i in instance_service.list_radarr(session)],
            "sonarr": [_view(i) for i in sonarr_instance_service.list_sonarr(session)],
            "seerr": [_view(i) for i in seerr_instance_service.list_seerr(session)],
            "saved": saved,
            "error": None,
        },
    )


@router.post("/instances/{kind}", response_class=HTMLResponse)
def add_instance(
    request: Request,
    session: DbSession,
    user: AdminUser,
    kind: str,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    api_key: Annotated[str, Form()],
    seerr_kind: Annotated[str, Form()] = "overseerr",
):
    service = _service(kind)
    fields = {"name": name.strip(), "url": url.strip(), "api_key": api_key.strip()}
    if kind == "seerr":
        fields["kind"] = seerr_kind if seerr_kind in ("overseerr", "jellyseerr") else "overseerr"
    creator = getattr(service, f"create_{kind}")
    creator(session, **fields)
    return RedirectResponse(_url("/instances?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/instances/{kind}/{instance_id}/delete", response_class=HTMLResponse)
def remove_instance(session: DbSession, user: AdminUser, kind: str, instance_id: int):
    getattr(_service(kind), f"delete_{kind}")(session, instance_id)
    return RedirectResponse(_url("/instances?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/instances/{kind}/{instance_id}/default", response_class=HTMLResponse)
def make_default(session: DbSession, user: AdminUser, kind: str, instance_id: int):
    _service(kind).set_default(session, instance_id)
    return RedirectResponse(_url("/instances?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/instances/{kind}/{instance_id}/test", response_class=HTMLResponse)
def test_instance(
    request: Request, session: DbSession, user: RequiredUser, kind: str, instance_id: int
):
    service = _service(kind)
    instance = getattr(service, f"get_{kind}")(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such instance.")

    context: dict = {"user": user, "ok": False, "version": "", "error": ""}
    try:
        context.update(ok=True, version=service.client_for(instance).test_connection())
    except (RadarrError, SonarrError, SeerrError) as exc:
        context["error"] = str(exc)

    return get_templates().TemplateResponse(request, "partials/instance_test.html", context)

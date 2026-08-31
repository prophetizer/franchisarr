"""Web UI for the movie side: collections, gaps, dismiss/exclude, and the add dialog.

These are the first real screens, so a note on how they're built: nothing here sets a colour.
Everything comes from Pico's variables, which `theme-adapter.css` remaps when an external theme
is configured. That's why theming was built before the screens rather than after -- retrofitting
would have meant auditing every one of these templates for hardcoded values.

Interactions use htmx against small partials rather than full page reloads, so dismissing a film
re-renders one list instead of the page.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.clients.radarr_client import RadarrError
from app.config import get_settings
from app.models import CollectionExclude, DismissedItem, ItemType, TmdbCollection
from app.services import add_service, instance_service, movie_gap_service
from app.services.settings_service import SettingKey, get_setting
from app.templating import get_templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


def _gap_or_404(session, user, collection_id: int):
    for gap in movie_gap_service.collection_gaps(session, user.id):
        if gap.collection_id == collection_id:
            return gap
    # A collection with nothing owned isn't listed at all, which is a 404 as far as the UI goes.
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such collection.")


@router.get("/collections", response_class=HTMLResponse)
def collections(request: Request, session: DbSession, user: RequiredUser):
    gaps = movie_gap_service.collections_with_gaps(session, user.id)
    return get_templates().TemplateResponse(
        request,
        "collections.html",
        {
            "user": user,
            "gaps": gaps,
            "total_missing": sum(len(gap.missing) for gap in gaps),
            # Distinguishes "you have no gaps" from "you haven't scanned yet", which look
            # identical otherwise and mean completely different things.
            "scanned": session.get(TmdbCollection, 0) is not None
            or bool(movie_gap_service.collection_gaps(session, user.id))
            or bool(movie_gap_service.owned_tmdb_ids(session)),
        },
    )


@router.get("/collections/{collection_id}", response_class=HTMLResponse)
def collection_detail(
    request: Request, session: DbSession, user: RequiredUser, collection_id: int
):
    gap = _gap_or_404(session, user, collection_id)
    return get_templates().TemplateResponse(
        request, "collection_detail.html", {"user": user, "gap": gap}
    )


def _missing_list(request: Request, session, user, collection_id: int) -> HTMLResponse:
    """Re-render just the missing list, for htmx to swap in."""
    gap = _gap_or_404(session, user, collection_id)
    return get_templates().TemplateResponse(
        request, "partials/missing_list.html", {"user": user, "gap": gap}
    )


@router.post("/collections/{collection_id}/dismiss/{tmdb_id}", response_class=HTMLResponse)
def dismiss(
    request: Request, session: DbSession, user: RequiredUser, collection_id: int, tmdb_id: int
):
    """Hide a film from this user's lists. Personal preference, not shared."""
    existing = movie_gap_service.dismissed_ids(session, user.id)
    if tmdb_id not in existing:
        session.add(
            DismissedItem(user_id=user.id, item_type=ItemType.MOVIE.value, tmdb_id=tmdb_id)
        )
        session.commit()
        logger.info("User %s dismissed tmdb:%s", user.id, tmdb_id)
    return _missing_list(request, session, user, collection_id)


@router.post("/collections/{collection_id}/exclude/{tmdb_id}", response_class=HTMLResponse)
def exclude(
    request: Request, session: DbSession, user: RequiredUser, collection_id: int, tmdb_id: int
):
    """Mark a film as not really part of this collection -- a TMDb data correction, shared by
    everyone, and scoped to this one collection rather than to the user's whole view."""
    if tmdb_id not in movie_gap_service.excluded_ids(session, collection_id):
        session.add(
            CollectionExclude(
                tmdb_collection_id=collection_id,
                tmdb_movie_id=tmdb_id,
                added_by_user_id=user.id,
            )
        )
        session.commit()
        logger.info("Excluded tmdb:%s from collection %s", tmdb_id, collection_id)
    return _missing_list(request, session, user, collection_id)


# ---------------------------------------------------------------------- add dialog


def _film_title(session, tmdb_id: int) -> str:
    for gap in movie_gap_service.collection_gaps(session):
        for movie in gap.missing + gap.upcoming:
            if movie.tmdb_id == tmdb_id:
                return movie.title
    return f"TMDb {tmdb_id}"


@router.get("/add/close", response_class=HTMLResponse)
def close_dialog() -> HTMLResponse:
    """htmx swaps this empty response in to dismiss the dialog."""
    return HTMLResponse("")


@router.get("/add/{tmdb_id}", response_class=HTMLResponse)
def add_dialog(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    tmdb_id: int,
    instance_id: int | None = None,
):
    """Build the add dialog, fetching profiles and root folders live from the chosen instance."""
    instances = instance_service.list_radarr(session)
    selected = (
        instance_service.get_radarr(session, instance_id)
        if instance_id
        else instance_service.preferred_instance(session, user)
    )

    options: dict = {"ok": False, "error": "", "quality_profiles": [], "root_folders": []}
    if selected is not None:
        client = instance_service.client_for(selected)
        try:
            options = {
                "ok": True,
                "error": "",
                "quality_profiles": client.quality_profiles(),
                "root_folders": client.root_folders(),
                "default_quality_profile_id": selected.default_quality_profile_id,
                "default_root_folder": selected.default_root_folder,
            }
        except RadarrError as exc:
            options["error"] = str(exc)

    return get_templates().TemplateResponse(
        request,
        "partials/add_dialog.html",
        {
            "user": user,
            "tmdb_id": tmdb_id,
            "title": _film_title(session, tmdb_id),
            "instances": instances,
            "selected": selected,
            "options": options,
        },
    )


@router.post("/add", response_class=HTMLResponse)
def submit_add(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    tmdb_id: Annotated[int, Form()],
    instance_id: Annotated[int, Form()],
    quality_profile_id: Annotated[int, Form()],
    root_folder_path: Annotated[str, Form()],
    search_on_add: Annotated[bool, Form()] = False,
):
    instance = instance_service.get_radarr(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such instance.")

    context: dict = {"user": user, "added": False, "error": "", "title": "", "instance": "",
                     "searched": False}
    try:
        result = add_service.add_movie(
            session,
            instance=instance,
            tmdb_id=tmdb_id,
            user=user,
            quality_profile_id=quality_profile_id,
            root_folder_path=root_folder_path,
            search_on_add=search_on_add,
        )
        context.update(
            added=True, title=result.title, instance=result.instance_name,
            searched=result.searched,
        )
    except add_service.AddFailed as exc:
        context["error"] = str(exc)

    return get_templates().TemplateResponse(request, "partials/add_result.html", context)


# ---------------------------------------------------------------------- settings


def _settings_context(session, user, **extra) -> dict:
    """One place that assembles the settings page, so a new field can't be added to the template
    and forgotten in one of the handlers that renders it."""
    from app.models import WebhookFormat
    from app.services import scheduler as scheduler_service
    from app.services.theme_service import SUGGESTED_THEMES, get_theme_url

    cron = get_setting(session, SettingKey.SCAN_SCHEDULE_CRON) or ""
    context = {
        "user": user,
        "current_theme_url": get_theme_url(session),
        "suggested": SUGGESTED_THEMES,
        "current_cron": cron,
        "schedule_description": scheduler_service.describe(cron),
        "current_webhook_url": get_setting(session, SettingKey.WEBHOOK_URL) or "",
        "current_webhook_format": get_setting(session, SettingKey.WEBHOOK_FORMAT) or "generic",
        "webhook_formats": [f.value for f in WebhookFormat],
        "saved": False,
        "error": None,
    }
    context.update(extra)
    return context


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: DbSession, user: RequiredUser, saved: bool = False):
    from app.services.theme_service import SUGGESTED_THEMES, get_theme_url

    return get_templates().TemplateResponse(
        request, "settings.html", _settings_context(session, user, saved=saved)
    )


@router.post("/settings", response_class=HTMLResponse)
def save_settings(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    theme_url: Annotated[str, Form()] = "",
):
    from app.services.theme_service import InvalidThemeUrl, set_theme_url

    try:
        set_theme_url(session, theme_url)
    except InvalidThemeUrl as exc:
        return get_templates().TemplateResponse(
            request,
            "settings.html",
            _settings_context(session, user, error=str(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(_url("/settings?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/schedule", response_class=HTMLResponse)
def save_schedule(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    scan_schedule_cron: Annotated[str, Form()] = "",
):
    """Save the scan schedule and apply it immediately, so the page can't disagree with reality."""
    from app.services import scan_job
    from app.services import scheduler as scheduler_service
    from app.services.settings_service import set_setting

    try:
        scheduler_service.validate_cron(scan_schedule_cron)
    except scheduler_service.InvalidSchedule as exc:
        return get_templates().TemplateResponse(
            request,
            "settings.html",
            _settings_context(session, user, error=str(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    was_unscheduled = not (get_setting(session, SettingKey.SCAN_SCHEDULE_CRON) or "").strip()
    set_setting(session, SettingKey.SCAN_SCHEDULE_CRON, scan_schedule_cron.strip())
    session.commit()
    scheduler_service.apply_schedule(scan_schedule_cron)

    # Turning scheduling on for the first time shouldn't make the first run announce the entire
    # existing backlog -- that's the state of the world, not news.
    if was_unscheduled and scan_schedule_cron.strip():
        scan_job.prime_seen_gaps(session)

    return RedirectResponse(_url("/settings?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/webhook", response_class=HTMLResponse)
def save_webhook(
    request: Request,
    session: DbSession,
    user: RequiredUser,
    webhook_url: Annotated[str, Form()] = "",
    webhook_format: Annotated[str, Form()] = "generic",
    test: Annotated[str, Form()] = "",
):
    from app.services import notifier
    from app.services.settings_service import set_setting

    set_setting(session, SettingKey.WEBHOOK_URL, webhook_url.strip())
    set_setting(session, SettingKey.WEBHOOK_FORMAT, webhook_format)
    session.commit()

    if test and webhook_url.strip():
        sample = notifier.ScanReport(
            new_movies=[notifier.NewItem("movie", 0, "A test notification from Franchisarr",
                                         "no action needed")]
        )
        delivered = notifier.send(webhook_url.strip(), sample, webhook_format)
        return get_templates().TemplateResponse(
            request,
            "settings.html",
            _settings_context(
                session, user,
                saved=delivered,
                error=None if delivered else "Couldn't deliver the test — check the URL.",
            ),
        )

    return RedirectResponse(_url("/settings?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/scan", response_class=HTMLResponse)
def trigger_scan(request: Request, session: DbSession, user: RequiredUser):
    """Kick off a scan from the empty-state button.

    Synchronous, which is honest but slow -- the browser waits. Phase 8 moves scanning onto the
    scheduler and this becomes a trigger rather than the thing itself.
    """
    from app.clients.plex_client import PlexClient
    from app.clients.tmdb_client import TmdbClient
    from app.services import scan_service

    plex_url = get_setting(session, SettingKey.PLEX_URL)
    plex_token = get_setting(session, SettingKey.PLEX_TOKEN)
    tmdb_key = get_setting(session, SettingKey.TMDB_API_KEY)

    if not (plex_url and plex_token and tmdb_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plex and TMDb both need configuring before a scan can run.",
        )

    scan_service.scan_movie_libraries(
        session, PlexClient(plex_url, plex_token), TmdbClient(tmdb_key)
    )
    return RedirectResponse(_url("/collections"), status_code=status.HTTP_303_SEE_OTHER)

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

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse

from sqlmodel import col, select

from app.auth.dependencies import AdminUser, DbSession, RequiredUser
from app.clients.radarr_client import RadarrError
from app.config import get_settings
from app.models import CollectionExclude, DismissedItem, ItemType, TmdbCollection
from app.services import add_service, instance_service, movie_gap_service, seerr_instance_service
from app.services.settings_service import SettingKey, get_setting
from app.templating import get_templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _url(path: str) -> str:
    return f"{get_settings().base_url}{path}"


def _gap_or_404(session, user, collection_id: int):
    for gap in movie_gap_service.collection_gaps(session, user.id, only={collection_id}):
        if gap.collection_id == collection_id:
            return gap
    # A collection with nothing owned isn't listed at all, which is a 404 as far as the UI goes.
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such collection.")


@router.get("/collections", response_class=HTMLResponse)
def collections(
    request: Request, session: DbSession, user: RequiredUser, sort: str | None = None,
    started: bool = False, page: int = 1, dir: str | None = None,  # noqa: A002 - the query parameter's name
):
    from app.services import pagination, scan_state, sorting

    current = sorting.resolve(session, user.id, "collections", sort, dir)
    gaps = movie_gap_service.collections_with_gaps(session, user.id)
    # The filter is offered only once a server has reported watched state at all; before that
    # it would hide everything and look like a bug.
    watched_known = any(movie.watched is not None for gap in gaps for movie in gap.owned)
    if started and watched_known:
        gaps = [gap for gap in gaps if gap.started]
    gaps = sorting.sort_groups(gaps, "collections", current)
    started_on = started and watched_known
    # The totals below describe every collection, not the page -- they are counted before the
    # slice for exactly that reason.
    pager = pagination.paginate(
        gaps, page, path="/collections",
        # The filter only applies when watched state is known, so the link carries it only
        # then -- otherwise page 2 would claim a filter the page is not applying.
        params={"sort": current[0], "dir": current[1], "started": 1 if started_on else None},
    )
    return get_templates().TemplateResponse(
        request,
        "collections.html",
        {
            "user": user,
            "progress": scan_state.current(),
            "gaps": pager.items,
            "pager": pager,
            "started": started and watched_known,
            "watched_known": watched_known,
            "total_missing": sum(len(gap.missing) for gap in gaps),
            "total_hidden": sum(len(gap.hidden) for gap in gaps),
            "sort_qs": f"sort={current[0]}&dir={current[1]}",
            "sort_ctl": sorting.control("collections", current, _url("/collections"),
                                        hidden={"started": 1 if started_on else None}),
            "min_rating": movie_gap_service.min_gap_rating(session),
            # Distinguishes "you have no gaps" from "you haven't scanned yet", which look
            # identical otherwise and mean completely different things.
            "scanned": session.exec(select(TmdbCollection.tmdb_collection_id).limit(1)).first() is not None
            or bool(movie_gap_service.owned_tmdb_ids(session, all_servers=True)),
        },
    )


@router.get("/upcoming", response_class=HTMLResponse)
def upcoming(request: Request, session: DbSession, user: RequiredUser, page: int = 1,
             sort: str | None = None, dir: str | None = None):  # noqa: A002
    """Announced films in franchises the user owns part of, soonest first.

    The one thing no *arr calendar can show: Radarr knows what has been added, this knows what
    the user would want added, because it knows what they already have.
    """
    from datetime import date

    from app.services import pagination, sorting, upcoming_service

    current = sorting.resolve(session, user.id, "upcoming", sort, dir)
    films = sorting.sort_upcoming(upcoming_service.upcoming_films(session, user.id), current)
    today = date.today()
    soon = sum(1 for f in films if f.days_until(today) is not None and 0 <= f.days_until(today) <= 90)
    pager = pagination.paginate(films, page, path="/upcoming", params={"sort": current[0], "dir": current[1]})
    return get_templates().TemplateResponse(
        request,
        "upcoming.html",
        {"user": user, "films": pager.items, "today": today, "soon": soon, "pager": pager,
         "sort_ctl": sorting.control("upcoming", current, _url("/upcoming"))},
    )


@router.post("/collections/rating-filter")
def set_rating_filter(
    session: DbSession, user: AdminUser, min_rating: Annotated[str, Form()] = "0"
):
    """Set the household's rating floor. A shared setting, like the dedup toggle, because the
    people in one household share one library -- and one opinion of Hellraiser IX is enough."""
    from app.services.settings_service import SettingKey, set_setting

    try:
        value = max(0.0, min(10.0, float(min_rating or 0)))
    except ValueError:
        value = 0.0
    set_setting(session, SettingKey.MIN_GAP_RATING, f"{value:g}")
    session.commit()
    return RedirectResponse(_url("/collections"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/collections/{collection_id}", response_class=HTMLResponse)
def collection_detail(
    request: Request, session: DbSession, user: RequiredUser, collection_id: int,
    sort: str | None = None, dir: str | None = None,  # noqa: A002
):
    gap = _gap_or_404(session, user, collection_id)
    from app.services import media_server_service, playlist_service, sorting

    detail_sort = sorting.resolve(session, user.id, "detail", sort, dir)

    return get_templates().TemplateResponse(
        request, "collection_detail.html",
        {"user": user, "gap": gap,
         "multi_server": len(media_server_service.list_servers(session)) > 1,
         "can_playlist": playlist_service.available(session) and bool(gap.owned),
         "playlist_servers": playlist_service.targets(session),
         "detail_sort": detail_sort,
         "sort_ctl": sorting.control("detail", detail_sort, _url(f"/collections/{collection_id}"))}
    )


def _missing_list(request: Request, session, user, collection_id: int) -> HTMLResponse:
    """Re-render just the missing list, for htmx to swap in."""
    from app.services import sorting

    gap = _gap_or_404(session, user, collection_id)
    return get_templates().TemplateResponse(
        request, "partials/missing_list.html",
        {"user": user, "gap": gap, "detail_sort": sorting.resolve(session, user.id, "detail", None)},
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
    request: Request, session: DbSession, user: AdminUser, collection_id: int, tmdb_id: int
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
    """The title the dialog shows. The collection cache has it for any film in a collection;
    a film reached from a show it relates to is in no collection the user owns part of."""
    from app.models import CrossMediaMapping, TmdbCollectionMovie

    title = session.exec(
        select(TmdbCollectionMovie.title).where(col(TmdbCollectionMovie.tmdb_movie_id) == tmdb_id)
    ).first()
    if title:
        return title
    row = session.exec(
        select(CrossMediaMapping).where(col(CrossMediaMapping.target_tmdb_id) == tmdb_id)
    ).first()
    return row.target_title if row else f"TMDb {tmdb_id}"


@router.get("/add/close", response_class=HTMLResponse)
def close_dialog() -> HTMLResponse:
    """htmx swaps this empty response in to dismiss the dialog."""
    return HTMLResponse("")


@router.get("/add/{tmdb_id}", response_class=HTMLResponse)
def add_dialog(
    request: Request,
    session: DbSession,
    user: AdminUser,
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
            "seerr_instances": seerr_instance_service.list_seerr(session),
        },
    )


@router.post("/add/request", response_class=HTMLResponse)
def submit_request(
    request: Request,
    session: DbSession,
    user: AdminUser,
    tmdb_id: Annotated[int, Form()],
    seerr_id: Annotated[int, Form()],
):
    """Ask Seerr for the film instead of adding it to a Radarr directly."""
    instance = seerr_instance_service.get_seerr(session, seerr_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such instance.")

    context: dict = {"user": user, "added": False, "requested": True, "error": "", "title": "",
                     "instance": instance.name, "needs_approval": False}
    try:
        result = add_service.request_via_seerr(
            session, instance=instance, item_type=ItemType.MOVIE.value, tmdb_id=tmdb_id,
            title=_film_title(session, tmdb_id), user=user,
        )
        context.update(added=True, title=result.title, needs_approval=result.needs_approval)
    except add_service.AddFailed as exc:
        context["error"] = str(exc)
    return get_templates().TemplateResponse(request, "partials/add_result.html", context)


@router.post("/add", response_class=HTMLResponse)
def submit_add(
    request: Request,
    session: DbSession,
    user: AdminUser,
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


def _update_status(session=None):
    """Cached so the settings page doesn't call out on every render. None when the check is
    switched off -- and then no request is made at all."""
    from app.services import update_checker

    global _UPDATE_CACHE
    if not update_checker.enabled(session):
        return None
    if _UPDATE_CACHE is None:
        _UPDATE_CACHE = update_checker.check(update_checker.releases_url(session))
    return _UPDATE_CACHE


_UPDATE_CACHE = None


def _update_check_enabled(session) -> bool:
    from app.services import update_checker

    return update_checker.enabled(session)


def _members_allowed(session) -> bool:
    from app.services.auth_service import members_allowed

    return members_allowed(session)


def _update_check_forced() -> bool:
    from app.services import update_checker

    return update_checker.forced_by_env()


@router.post("/settings/update-check")
def set_update_check(session: DbSession, user: AdminUser,
                     enabled: Annotated[str, Form()] = ""):
    """The one outbound request the user didn't configure, and so the one they can turn off."""
    from app.services.settings_service import set_setting

    global _UPDATE_CACHE
    set_setting(session, SettingKey.UPDATE_CHECK, "true" if enabled else "false")
    session.commit()
    _UPDATE_CACHE = None     # a re-enabled check should ask afresh, not show a stale answer
    return RedirectResponse(_url("/settings?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/members")
def set_members(session: DbSession, user: AdminUser, enabled: Annotated[str, Form()] = ""):
    """Whether non-administrators may sign in. Off by default; see auth_service.members_allowed."""
    from app.services.settings_service import set_setting

    set_setting(session, SettingKey.ALLOW_MEMBER_SIGNIN, "true" if enabled else "false")
    session.commit()
    logger.info("Member sign-in %s by user %s", "allowed" if enabled else "turned off", user.id)
    return RedirectResponse(_url("/settings?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


def _mask(value: str) -> str:
    from app.logging_config import mask_secret

    return mask_secret(value.strip())


def _settings_context(session, user, **extra) -> dict:
    """One place that assembles the settings page, so a new field can't be added to the template
    and forgotten in one of the handlers that renders it."""
    from app.models import WebhookFormat
    from app.services import scheduler as scheduler_service
    from app.services.theme_service import resolve as resolve_theme

    cron = get_setting(session, SettingKey.SCAN_SCHEDULE_CRON) or ""
    context = {
        "user": user,
        "theme_config": resolve_theme(),
        "current_cron": cron,
        "schedule_description": scheduler_service.describe(cron),
        "webhook_masked": _mask(get_setting(session, SettingKey.WEBHOOK_URL) or ""),
        "tmdb_masked": _mask(get_setting(session, SettingKey.TMDB_API_KEY) or ""),
        "fanart_masked": _mask(get_setting(session, SettingKey.FANART_API_KEY) or ""),
        "key_note": None,
        "current_webhook_format": get_setting(session, SettingKey.WEBHOOK_FORMAT) or "generic",
        "webhook_formats": [
            (WebhookFormat.GENERIC.value, "Generic webhook (JSON)"),
            (WebhookFormat.DISCORD.value, "Discord webhook"),
            (WebhookFormat.SLACK.value, "Slack webhook"),
            (WebhookFormat.APPRISE.value, "Apprise — 100+ services"),
            (WebhookFormat.APPRISE_API.value, "apprise-api (self-hosted)"),
        ],
        "saved": False,
        "error": None,
        "import_note": None,
        "update": _update_status(session),
        "update_check_enabled": _update_check_enabled(session),
        "members_allowed": _members_allowed(session),
        "update_check_forced": _update_check_forced(),
        # Import lists: the URLs Radarr and Sonarr can poll. The key is never rendered; the page
        # shows whether one exists and mints a new one on request, shown once.
        "has_api_key": bool(user.api_key),
        "new_api_key": None,
        "list_base": get_settings().base_url + "/api/lists",
        "list_names": ["collections", "upcoming", "directors", "franchises", "films", "shows"],
    }
    context.update(extra)
    return context


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: DbSession, user: AdminUser, saved: bool = False):
    return get_templates().TemplateResponse(
        request, "settings.html", _settings_context(session, user, saved=saved)
    )


@router.post("/settings/keys", response_class=HTMLResponse)
def settings_keys(
    request: Request,
    session: DbSession,
    user: AdminUser,
    tmdb_api_key: Annotated[str, Form()] = "",
    fanart_api_key: Annotated[str, Form()] = "",
    fanart_clear: Annotated[str, Form()] = "",
):
    """The TMDb and fanart.tv keys. Until 0.33.1 they could only come from the environment on
    first boot, so an install started without TMDB_API_KEY had no way to add it (a Reddit
    report). Blank keeps the saved key, as on every credential form. A new TMDb key is checked
    before it's saved: a wrong one would otherwise show up only as a scan failing on every film."""
    from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError
    from app.logging_config import register_secret
    from app.services.settings_service import set_setting

    note = None
    tmdb = tmdb_api_key.strip()
    if tmdb:
        try:
            TmdbClient(tmdb).validate_key()
        except TmdbAuthError as exc:
            return get_templates().TemplateResponse(request, "settings.html", _settings_context(
                session, user, error=f"Not saved: {exc}"))
        except TmdbError:
            note = "Saved, but TMDb couldn't be reached to check the key just now."
        register_secret(tmdb)
        set_setting(session, SettingKey.TMDB_API_KEY, tmdb)
    fanart = fanart_api_key.strip()
    if fanart_clear:
        set_setting(session, SettingKey.FANART_API_KEY, "")
    elif fanart:
        register_secret(fanart)
        set_setting(session, SettingKey.FANART_API_KEY, fanart)
    session.commit()
    if note:
        return get_templates().TemplateResponse(request, "settings.html", _settings_context(
            session, user, key_note=note))
    return RedirectResponse(_url("/settings?saved=1#keys"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/api-key", response_class=HTMLResponse)
def settings_new_api_key(request: Request, session: DbSession, user: AdminUser):
    """Mint the per-user key the import lists and the CLI use. Shown once, in full, here."""
    from app.auth.api_keys import generate_api_key

    key = generate_api_key(session, user)
    session.commit()
    return get_templates().TemplateResponse(
        request, "settings.html", _settings_context(session, user, new_api_key=key)
    )


@router.post("/settings/api-key/revoke")
def settings_revoke_api_key(session: DbSession, user: AdminUser):
    from app.auth.api_keys import revoke_api_key

    revoke_api_key(session, user)
    return RedirectResponse(_url("/settings?saved=1"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/schedule", response_class=HTMLResponse)
def save_schedule(
    request: Request,
    session: DbSession,
    user: AdminUser,
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
    user: AdminUser,
    webhook_url: Annotated[str, Form()] = "",
    webhook_format: Annotated[str, Form()] = "generic",
    test: Annotated[str, Form()] = "",
    clear: Annotated[str, Form()] = "",
):
    from app.logging_config import register_secret
    from app.models import WebhookFormat
    from app.services import notifier
    from app.services.settings_service import set_setting

    if webhook_format not in {f.value for f in WebhookFormat}:
        return get_templates().TemplateResponse(
            request, "settings.html",
            _settings_context(session, user, error="Unknown notification format."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # Blank keeps the saved URL (the page never shows it); the checkbox removes it.
    if clear:
        set_setting(session, SettingKey.WEBHOOK_URL, "")
    elif webhook_url.strip():
        set_setting(session, SettingKey.WEBHOOK_URL, webhook_url.strip())
        # A Discord webhook URL or an Apprise URL is a credential; keep it out of the logs.
        register_secret(webhook_url.strip())
    set_setting(session, SettingKey.WEBHOOK_FORMAT, webhook_format)
    session.commit()
    webhook_url = get_setting(session, SettingKey.WEBHOOK_URL) or ""

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


def scan_prerequisites(session) -> list[tuple[str, str, str]]:  # noqa: ANN001
    """What's missing before a scan can run, as (reason, page, link text); empty when nothing."""
    from app.services import media_server_service

    missing = []
    if not media_server_service.is_configured(session):
        missing.append(("No media server is set up and switched on yet.", "/media-servers", "Add one under Servers"))
    if not (get_setting(session, SettingKey.TMDB_API_KEY) or "").strip():
        missing.append(("No TMDb API key yet.", "/settings#keys", "Add it in Settings"))
    return missing


@router.post("/scan", response_class=HTMLResponse)
def trigger_scan(
    request: Request,
    session: DbSession,
    user: AdminUser,
    refresh: Annotated[str, Form()] = "",
):
    """Start a scan and return immediately.

    This used to run the scan inside the request. On a real library that is minutes of waiting on
    Plex and TMDb with no sign of life, and the page eventually timed out — the work carried on
    invisibly, or died with the request. It now starts a background task and hands back a panel
    that polls for progress.
    """
    from app.services import scan_job, scan_state

    # Refused with a 200 and the reason in the panel, not a 409: htmx drops an error response,
    # so the button did nothing and said nothing (a Reddit report, 0.33.1).
    missing = scan_prerequisites(session)
    if missing:
        logger.warning("Scan not started: %s", "; ".join(text for text, _, _ in missing))
        return get_templates().TemplateResponse(request, "partials/scan_status.html", {
            "user": user, "progress": scan_state.current(), "refused": missing})

    # A second click while one is running is a no-op rather than an error: the panel it gets back
    # shows the scan already in progress, which is what the person wanted to see anyway.
    scan_job.run_in_background("manual", force_refresh=bool(refresh))

    return get_templates().TemplateResponse(
        request, "partials/scan_status.html", {"user": user, "progress": scan_state.current()}
    )


@router.get("/scan/status", response_class=HTMLResponse)
def scan_status(request: Request, session: DbSession, user: RequiredUser):
    from app.services import scan_state

    return get_templates().TemplateResponse(
        request, "partials/scan_status.html", {"user": user, "progress": scan_state.current()}
    )


# ---------------------------------------------------------------------- activity log


@router.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request, session: DbSession, user: RequiredUser, page: int = 1):
    """What Franchisarr added, newest first."""
    from app.models import RadarrInstance, SeerrInstance, SonarrInstance, User
    from app.services import activity_log

    page = min(max(1, page), 10**6)      # a huge page number overflowed SQLite's integer
    per_page = 50
    entries = activity_log.recent(session, limit=per_page + 1, offset=(page - 1) * per_page)
    has_more = len(entries) > per_page

    rows = []
    for entry in entries[:per_page]:
        if entry.trigger_source == "scheduled":
            who = "Scheduled scan"
        elif entry.triggered_by is None:
            # NULL with trigger_source='manual' means the account was deleted, not the scheduler.
            who = "A deleted account"
        else:
            account = session.get(User, entry.triggered_by)
            who = (account.external_username or account.local_username) if account else "Unknown"

        if entry.target == "seerr":
            model = SeerrInstance
        else:
            model = RadarrInstance if entry.item_type == "movie" else SonarrInstance
        instance = session.get(model, entry.instance_id) if entry.instance_id else None

        rows.append({
            "when": entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            "title": entry.title,
            "item_type": entry.item_type,
            "instance": instance.name if instance else "—",
            "who": who,
        })

    return get_templates().TemplateResponse(
        request,
        "activity.html",
        {"user": user, "entries": rows, "page": page, "has_more": has_more},
    )


# ---------------------------------------------------------------------- config backup


@router.get("/settings/export")
def export_config(session: DbSession, user: AdminUser, redact: bool = False):
    """Download the configuration as JSON."""
    import json

    from fastapi.responses import Response

    from app.services import config_backup

    document = config_backup.export_config(session, redact=redact)
    suffix = "-redacted" if redact else ""
    return Response(
        content=json.dumps(document, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="franchisarr-config{suffix}.json"'
        },
    )


@router.get("/settings/diagnostics")
def diagnostics(session: DbSession, user: AdminUser):
    """A redacted bundle for a bug report: versions, counts, unmatched titles, last scan."""
    from fastapi.responses import Response

    from app.services import diagnostics as diagnostics_service

    return Response(
        content=diagnostics_service.render(session),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="franchisarr-diagnostics.json"'},
    )


@router.post("/settings/import", response_class=HTMLResponse)
async def import_config(
    request: Request,
    session: DbSession,
    user: AdminUser,
    backup: Annotated[UploadFile, File()],
    replace: Annotated[str, Form()] = "",
):
    import json

    from app.services import config_backup

    try:
        document = json.loads((await backup.read()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return get_templates().TemplateResponse(
            request,
            "settings.html",
            _settings_context(session, user, error="That file isn't valid JSON."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        counts = config_backup.import_config(session, document, replace=bool(replace))
    except config_backup.InvalidBackup as exc:
        return get_templates().TemplateResponse(
            request,
            "settings.html",
            _settings_context(session, user, error=str(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    note = (
        f"Imported {counts['settings']} setting(s), {counts['radarr']} Radarr and "
        f"{counts['sonarr']} Sonarr instance(s), {counts['mappings']} mapping(s)."
    )
    if counts["already_present"]:
        note += f" {counts['already_present']} item(s) were already present and left alone."
    if counts["skipped_redacted"]:
        note += (
            f" {counts['skipped_redacted']} item(s) were skipped because the export was "
            f"redacted — those need entering by hand."
        )
    if counts["media_servers"]:
        note += (
            f" {counts['media_servers']} media server(s) were added switched off: a server "
            f"decides who can sign in, so check each one on the Servers page and switch it on."
        )
    if counts["skipped_invalid"]:
        note += f" {counts['skipped_invalid']} item(s) were skipped as invalid or unknown."

    return get_templates().TemplateResponse(
        request, "settings.html", _settings_context(session, user, saved=True, import_note=note)
    )

"""JSON API.

The CLI and the web UI both come through here, which is the whole point of making the CLI an HTTP
client: there is one code path to keep correct, not two (PROJECT_PLAN.md decision log).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from pydantic import BaseModel

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import AdminUser, DbSession, RequiredUser
from app.clients.plex_client import PlexClient
from app.clients.radarr_client import RadarrClient, RadarrError
from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError
from app.services import activity_log, add_service, instance_service, movie_gap_service, scan_service
from app.services.settings_service import SettingKey, get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _plex(session) -> PlexClient:
    url = get_setting(session, SettingKey.PLEX_URL)
    token = get_setting(session, SettingKey.PLEX_TOKEN)
    if not url or not token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No Plex connection is configured yet.",
        )
    return PlexClient(url, token)


def _tmdb(session) -> TmdbClient:
    api_key = get_setting(session, SettingKey.TMDB_API_KEY)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No TMDb API key is configured yet. Add one from themoviedb.org.",
        )
    return TmdbClient(api_key)


@router.get("/me")
def whoami(user: RequiredUser) -> dict:
    return {
        "id": user.id,
        "username": user.plex_username or user.local_username,
        "is_admin": user.is_admin,
    }


@router.post("/me/api-key")
def issue_api_key(session: DbSession, user: RequiredUser) -> dict:
    """Generate a CLI credential. Shown in full once and never again."""
    return {
        "api_key": generate_api_key(session, user),
        "note": "Store this now — it is not shown again. Send it as an X-Api-Key header.",
    }


@router.get("/tmdb/test")
def test_tmdb(session: DbSession, user: RequiredUser) -> dict:
    """Check the configured TMDb key and explain precisely what's wrong if it fails."""
    try:
        _tmdb(session).validate_key()
    except TmdbAuthError as exc:
        return {"ok": False, "error": str(exc)}
    except TmdbError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@router.post("/scan/movies")
def scan_movies(session: DbSession, user: RequiredUser, force: bool = False) -> dict:
    """Re-walk the enabled movie libraries and refresh the TMDb cache.

    Synchronous for now: a scan of a few thousand films takes minutes, which is tolerable for a
    CLI invocation. Moving it onto the scheduler is Phase 8's job.
    """
    summary = scan_service.scan_movie_libraries(
        session, _plex(session), _tmdb(session), force_refresh=force
    )
    return {
        "libraries_scanned": summary.libraries_scanned,
        "items_seen": summary.items_seen,
        "matched": summary.matched,
        "needs_review": summary.needs_review,
        "unmatched": summary.unmatched,
        "removed": summary.removed,
        "collections_found": summary.collections_found,
        "tmdb_lookups": summary.tmdb_lookups,
        "errors": summary.errors,
    }


@router.get("/collections/gaps")
def collection_gaps(
    session: DbSession,
    user: RequiredUser,
    all: bool = False,
    instance_id: int | None = None,
) -> dict:
    """Collections the library partly owns. By default only those with something missing."""
    gaps = (
        movie_gap_service.collection_gaps(session, user.id, radarr_instance_id=instance_id)
        if all
        else movie_gap_service.collections_with_gaps(
            session, user.id, radarr_instance_id=instance_id
        )
    )
    return {
        "collections": [
            {
                "collection_id": gap.collection_id,
                "name": gap.name,
                "owned_count": len(gap.owned),
                "missing_count": len(gap.missing),
                "upcoming_count": len(gap.upcoming),
                "missing": [
                    {"tmdb_id": m.tmdb_id, "title": m.title, "year": m.release_year}
                    for m in gap.missing
                ],
                # Announced or scheduled but not out yet. Addable to Radarr (it will monitor and
                # grab on release) but not something to chase today.
                "upcoming": [
                    {
                        "tmdb_id": m.tmdb_id,
                        "title": m.title,
                        "year": m.release_year,
                        "release_date": m.release_date,
                    }
                    for m in gap.upcoming
                ],
            }
            for gap in gaps
        ]
    }


@router.get("/matches/review")
def matches_needing_review(session: DbSession, user: RequiredUser) -> dict:
    """Plausible but unconfirmed matches, plus items nothing matched at all."""
    return {
        "needs_review": [
            {
                "title": item.title,
                "year": item.year,
                "tmdb_id": item.tmdb_id,
                "confidence": item.match_confidence,
            }
            for item in movie_gap_service.items_needing_review(session)
        ],
        "unmatched": [
            {"title": item.title, "year": item.year}
            for item in movie_gap_service.unmatched_items(session)
        ],
    }


# ---------------------------------------------------------------------- Radarr instances


class RadarrInstanceIn(BaseModel):
    name: str
    url: str
    api_key: str
    default_root_folder: str | None = None
    default_quality_profile_id: int | None = None
    hide_if_queued: bool = True


def _instance_summary(instance, *, preferred_id: int | None = None) -> dict:
    """Never includes the API key. It is write-only from the API's point of view; the settings UI
    shows a mask and requires re-entry to change it (technical challenge #8)."""
    return {
        "id": instance.id,
        "name": instance.name,
        "url": instance.url,
        "default_root_folder": instance.default_root_folder,
        "default_quality_profile_id": instance.default_quality_profile_id,
        "is_default": instance.is_default,
        "hide_if_queued": instance.hide_if_queued,
        "preferred": instance.id == preferred_id,
    }


def _require_instance(session, instance_id: int):
    instance = instance_service.get_radarr(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such Radarr instance.")
    return instance


@router.get("/instances/radarr")
def list_instances(session: DbSession, user: RequiredUser) -> dict:
    preferred = instance_service.preferred_instance(session, user)
    return {
        "instances": [
            _instance_summary(instance, preferred_id=preferred.id if preferred else None)
            for instance in instance_service.list_radarr(session)
        ]
    }


@router.post("/instances/radarr", status_code=status.HTTP_201_CREATED)
def create_instance(session: DbSession, user: AdminUser, payload: RadarrInstanceIn) -> dict:
    instance = instance_service.create_radarr(session, **payload.model_dump())
    return _instance_summary(instance)


@router.delete("/instances/radarr/{instance_id}")
def delete_instance(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    _require_instance(session, instance_id)
    instance_service.delete_radarr(session, instance_id)
    return {"deleted": instance_id}


@router.post("/instances/radarr/{instance_id}/default")
def make_default(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    _require_instance(session, instance_id)
    instance_service.set_default(session, instance_id)
    return {"default": instance_id}


@router.get("/instances/radarr/{instance_id}/test")
def test_instance(session: DbSession, user: RequiredUser, instance_id: int) -> dict:
    instance = _require_instance(session, instance_id)
    try:
        return {"ok": True, "version": instance_service.client_for(instance).test_connection()}
    except RadarrError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/instances/radarr/{instance_id}/options")
def instance_options(session: DbSession, user: RequiredUser, instance_id: int) -> dict:
    """Quality profiles and root folders, fetched live at add time.

    Options are never stored -- only the chosen default is (PROJECT_PLAN.md section 5). An
    unreachable instance returns ok=false with a message rather than empty lists, so the add
    dialog can say "can't reach this instance" instead of silently offering nothing
    (technical challenge #15).
    """
    instance = _require_instance(session, instance_id)
    client = instance_service.client_for(instance)
    try:
        profiles = client.quality_profiles()
        folders = client.root_folders()
    except RadarrError as exc:
        return {"ok": False, "error": str(exc), "quality_profiles": [], "root_folders": []}

    return {
        "ok": True,
        "quality_profiles": [{"id": p.id, "name": p.name} for p in profiles],
        "root_folders": [
            {"path": f.path, "free_space": f.free_space, "label": f.free_space_label,
             "accessible": f.accessible}
            for f in folders
        ],
        "default_quality_profile_id": instance.default_quality_profile_id,
        "default_root_folder": instance.default_root_folder,
    }


@router.post("/instances/radarr/refresh")
def refresh_instances(session: DbSession, user: RequiredUser) -> dict:
    """Re-read what each instance holds, so gap views reflect it without live calls."""
    results = instance_service.refresh_all(session)
    return {
        "instances": [
            {"id": r.instance_id, "name": r.name, "movies": r.movies, "queued": r.queued,
             "ok": r.ok, "error": r.error}
            for r in results
        ]
    }


# ---------------------------------------------------------------------- adding


class AddMovieIn(BaseModel):
    tmdb_id: int
    instance_id: int | None = None
    quality_profile_id: int | None = None
    root_folder_path: str | None = None
    search_on_add: bool = True


@router.post("/radarr/add")
def add_movie(session: DbSession, user: RequiredUser, payload: AddMovieIn) -> dict:
    """Send one film to Radarr, monitored and searched immediately by default."""
    if payload.instance_id is not None:
        instance = _require_instance(session, payload.instance_id)
    else:
        instance = instance_service.preferred_instance(session, user)
        if instance is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No Radarr instance is configured yet.",
            )

    try:
        result = add_service.add_movie(
            session,
            instance=instance,
            tmdb_id=payload.tmdb_id,
            user=user,
            quality_profile_id=payload.quality_profile_id,
            root_folder_path=payload.root_folder_path,
            search_on_add=payload.search_on_add,
        )
    except add_service.AddFailed as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "added": True,
        "tmdb_id": result.tmdb_id,
        "title": result.title,
        "instance": result.instance_name,
        "searched": result.searched,
    }


@router.get("/activity")
def activity(session: DbSession, user: RequiredUser, limit: int = 50, offset: int = 0) -> dict:
    """What Franchisarr added, and when. Not download status -- that stays Radarr's history."""
    return {
        "total": activity_log.count(session),
        "note": "Franchisarr records the add only; see your Radarr instance's history for what "
                "happened afterwards.",
        "entries": [
            {
                "timestamp": entry.timestamp.isoformat(),
                "item_type": entry.item_type,
                "tmdb_id": entry.tmdb_id,
                "title": entry.title,
                "instance_id": entry.instance_id,
                "triggered_by": entry.triggered_by,
                "trigger_source": entry.trigger_source,
            }
            for entry in activity_log.recent(session, limit=limit, offset=offset)
        ],
    }

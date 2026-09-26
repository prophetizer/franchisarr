"""JSON API.

The CLI and the web UI both come through here, which is the whole point of making the CLI an HTTP
client: there is one code path to keep correct, not two (docs/DESIGN.md decision log).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from pydantic import BaseModel

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import AdminUser, DbSession, RequiredUser
from app.clients.radarr_client import RadarrClient, RadarrError
from app.clients.sonarr_client import MONITOR_MODE_LABELS, SonarrError
from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError
from app.services import (
    activity_log,
    add_service,
    instance_service,
    movie_gap_service,
    sonarr_instance_service,
    tv_spinoff_service,
)
from app.services.settings_service import SettingKey, get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _require_media_server(session) -> None:
    from app.services import media_server_service

    if not media_server_service.is_configured(session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=media_server_service.missing_message(session),
        )


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
        "username": user.external_username or user.local_username,
        "is_admin": user.is_admin,
    }


@router.post("/me/api-key")
def issue_api_key(session: DbSession, user: AdminUser) -> dict:
    """Generate a CLI credential. Shown in full once and never again."""
    return {
        "api_key": generate_api_key(session, user),
        "note": "Store this now — it is not shown again. Send it as an X-Api-Key header.",
    }


@router.get("/tmdb/test")
def test_tmdb(session: DbSession, user: AdminUser) -> dict:
    """Check the configured TMDb key and explain precisely what's wrong if it fails."""
    try:
        _tmdb(session).validate_key()
    except TmdbAuthError as exc:
        return {"ok": False, "error": str(exc)}
    except TmdbError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@router.post("/scan")
def start_scan(session: DbSession, user: AdminUser) -> dict:
    """Start a scan in the background and return at once.

    Scanning used to happen inside the request, which on a real library meant minutes of silence
    and then a timeout. Poll `/api/scan/status` for progress.
    """
    from app.services import scan_job, scan_state

    # Fail before starting rather than letting the background task discover it and report through
    # a status endpoint nobody is watching yet.
    _require_media_server(session)
    _tmdb(session)

    started = scan_job.run_in_background("api")
    return {"started": started, "already_running": not started, **_scan_status_dict()}


@router.get("/scan/status")
def scan_status(user: RequiredUser) -> dict:
    return _scan_status_dict()


def _scan_status_dict() -> dict:
    from app.services import scan_state

    progress = scan_state.current()
    return {
        "running": progress.running,
        "phase": progress.phase,
        "processed": progress.processed,
        "total": progress.total,
        "percent": progress.percent,
        "elapsed_seconds": progress.elapsed_seconds,
        "summary": progress.summary,
        "errors": list(progress.errors),
        "trigger": progress.trigger,
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


@router.get("/spinoffs")
def spinoffs(session: DbSession, user: RequiredUser) -> dict:
    """Spin-offs of shows in the library that the library doesn't have."""
    suggestions = tv_spinoff_service.missing_spinoffs(session, user.id)
    return {
        "suggestions": [
            {
                "source_show_tmdb_id": s.source_show_tmdb_id,
                "source_show_name": s.source_show_name,
                "tmdb_id": s.spinoff_tmdb_id,
                "name": s.spinoff_name,
                "year": s.first_air_year,
                "confidence": s.confidence,
            }
            for s in suggestions
        ],
        "mappings": len(tv_spinoff_service.list_mappings(session)),
    }


class SpinoffMappingIn(BaseModel):
    source_show_tmdb_id: int
    spinoff_show_tmdb_id: int


@router.post("/spinoffs/mappings", status_code=status.HTTP_201_CREATED)
def add_spinoff_mapping(
    session: DbSession, user: AdminUser, payload: SpinoffMappingIn
) -> dict:
    """Record a spin-off relationship. Always written as a local, confirmed mapping."""
    try:
        mapping = tv_spinoff_service.add_mapping(
            session,
            source_show_tmdb_id=payload.source_show_tmdb_id,
            spinoff_show_tmdb_id=payload.spinoff_show_tmdb_id,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if mapping is None:
        return {"created": False, "reason": "That mapping already exists."}
    return {"created": True, "id": mapping.id}


@router.get("/matches/review")
def matches_needing_review(session: DbSession, user: AdminUser) -> dict:
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
def list_instances(session: DbSession, user: AdminUser) -> dict:
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
def test_instance(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    instance = _require_instance(session, instance_id)
    try:
        return {"ok": True, "version": instance_service.client_for(instance).test_connection()}
    except RadarrError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/instances/radarr/{instance_id}/options")
def instance_options(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    """Quality profiles and root folders, fetched live at add time.

    Options are never stored -- only the chosen default is (docs/DESIGN.md section 5). An
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
def refresh_instances(session: DbSession, user: AdminUser) -> dict:
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
def add_movie(session: DbSession, user: AdminUser, payload: AddMovieIn) -> dict:
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


# ---------------------------------------------------------------------- Sonarr instances


class SonarrInstanceIn(BaseModel):
    name: str
    url: str
    api_key: str
    default_root_folder: str | None = None
    default_quality_profile_id: int | None = None
    default_monitor_mode: str = "all"
    hide_if_queued: bool = True


def _sonarr_summary(instance, *, preferred_id: int | None = None) -> dict:
    """Never includes the API key, for the same reason the Radarr one doesn't."""
    return {
        "id": instance.id,
        "name": instance.name,
        "url": instance.url,
        "default_root_folder": instance.default_root_folder,
        "default_quality_profile_id": instance.default_quality_profile_id,
        "default_monitor_mode": instance.default_monitor_mode,
        "is_default": instance.is_default,
        "hide_if_queued": instance.hide_if_queued,
        "preferred": instance.id == preferred_id,
    }


def _require_sonarr(session, instance_id: int):
    instance = sonarr_instance_service.get_sonarr(session, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such Sonarr instance.")
    return instance


@router.get("/instances/sonarr")
def list_sonarr_instances(session: DbSession, user: AdminUser) -> dict:
    preferred = sonarr_instance_service.preferred_instance(session, user)
    return {
        "instances": [
            _sonarr_summary(instance, preferred_id=preferred.id if preferred else None)
            for instance in sonarr_instance_service.list_sonarr(session)
        ],
        "monitor_modes": [{"value": v, "label": l} for v, l in MONITOR_MODE_LABELS.items()],
    }


@router.post("/instances/sonarr", status_code=status.HTTP_201_CREATED)
def create_sonarr_instance(session: DbSession, user: AdminUser, payload: SonarrInstanceIn) -> dict:
    instance = sonarr_instance_service.create_sonarr(session, **payload.model_dump())
    return _sonarr_summary(instance)


@router.delete("/instances/sonarr/{instance_id}")
def delete_sonarr_instance(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    _require_sonarr(session, instance_id)
    sonarr_instance_service.delete_sonarr(session, instance_id)
    return {"deleted": instance_id}


@router.post("/instances/sonarr/{instance_id}/default")
def make_sonarr_default(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    """Mirror of the Radarr endpoint. Its absence was an asymmetry in the API surface rather
    than a decision."""
    _require_sonarr(session, instance_id)
    sonarr_instance_service.set_default(session, instance_id)
    return {"default": instance_id}


@router.get("/instances/sonarr/{instance_id}/test")
def test_sonarr_instance(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    instance = _require_sonarr(session, instance_id)
    try:
        return {
            "ok": True,
            "version": sonarr_instance_service.client_for(instance).test_connection(),
        }
    except SonarrError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/instances/sonarr/{instance_id}/options")
def sonarr_instance_options(session: DbSession, user: AdminUser, instance_id: int) -> dict:
    instance = _require_sonarr(session, instance_id)
    client = sonarr_instance_service.client_for(instance)
    try:
        profiles = client.quality_profiles()
        folders = client.root_folders()
    except SonarrError as exc:
        return {"ok": False, "error": str(exc), "quality_profiles": [], "root_folders": []}

    return {
        "ok": True,
        "quality_profiles": [{"id": p.id, "name": p.name} for p in profiles],
        "root_folders": [
            {"path": f.path, "free_space": f.free_space, "label": f.free_space_label}
            for f in folders
        ],
        "default_quality_profile_id": instance.default_quality_profile_id,
        "default_root_folder": instance.default_root_folder,
        "default_monitor_mode": instance.default_monitor_mode,
        "monitor_modes": [{"value": v, "label": l} for v, l in MONITOR_MODE_LABELS.items()],
    }


@router.post("/instances/sonarr/refresh")
def refresh_sonarr_instances(session: DbSession, user: AdminUser) -> dict:
    results = sonarr_instance_service.refresh_all(session)
    return {
        "instances": [
            {"id": r.instance_id, "name": r.name, "series": r.series, "queued": r.queued,
             "ok": r.ok, "error": r.error}
            for r in results
        ]
    }


class AddSeriesIn(BaseModel):
    tmdb_id: int
    instance_id: int | None = None
    quality_profile_id: int | None = None
    root_folder_path: str | None = None
    monitor_mode: str | None = None
    search_on_add: bool = True


@router.post("/sonarr/add")
def add_series_endpoint(session: DbSession, user: AdminUser, payload: AddSeriesIn) -> dict:
    if payload.instance_id is not None:
        instance = _require_sonarr(session, payload.instance_id)
    else:
        instance = sonarr_instance_service.preferred_instance(session, user)
        if instance is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No Sonarr instance is configured yet.",
            )

    try:
        result = add_service.add_series(
            session,
            instance=instance,
            tmdb_id=payload.tmdb_id,
            user=user,
            quality_profile_id=payload.quality_profile_id,
            root_folder_path=payload.root_folder_path,
            monitor_mode=payload.monitor_mode,
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

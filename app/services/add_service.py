"""Sending a film to Radarr.

Deliberately thin, but it is the only place an add happens, so it is the only place that has to
get the surrounding obligations right: nothing is added without an explicit instance and profile,
every add is logged, and the user's choice of instance is remembered for next time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session

from app.clients.radarr_client import (
    MovieAlreadyAddedError,
    RadarrError,
)
from app.clients.sonarr_client import (
    SeriesAlreadyAddedError,
    SonarrError,
)
from app.models import (
    ItemType,
    MonitorMode,
    RadarrInstance,
    SonarrInstance,
    TriggerSource,
    User,
)
from app.services import activity_log, instance_service, sonarr_instance_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AddResult:
    tmdb_id: int
    title: str
    instance_id: int
    instance_name: str
    searched: bool


class AddFailed(RuntimeError):
    """Something stopped the add. The message is safe to show a user."""


def add_movie(
    session: Session,
    *,
    instance: RadarrInstance,
    tmdb_id: int,
    user: User | None = None,
    quality_profile_id: int | None = None,
    root_folder_path: str | None = None,
    search_on_add: bool = True,
    trigger_source: str = TriggerSource.MANUAL.value,
) -> AddResult:
    """Add one film, then record it.

    Falls back to the instance's saved defaults when the caller doesn't specify, which is what
    makes a CLI add possible without repeating the profile every time. If neither is available
    the add is refused rather than guessed at -- picking a quality profile on someone's behalf
    means downloading the wrong thing at the wrong size (technical challenge #15).
    """
    profile_id = quality_profile_id or instance.default_quality_profile_id
    root_folder = root_folder_path or instance.default_root_folder

    if not profile_id:
        raise AddFailed(
            f"No quality profile chosen, and {instance.name} has no default set."
        )
    if not root_folder:
        raise AddFailed(f"No root folder chosen, and {instance.name} has no default set.")

    client = instance_service.client_for(instance)
    try:
        added = client.add_movie(
            tmdb_id,
            quality_profile_id=profile_id,
            root_folder_path=root_folder,
            search_on_add=search_on_add,
        )
    except MovieAlreadyAddedError as exc:
        # Worth distinguishing: the gap list was simply out of date, not broken.
        raise AddFailed(str(exc)) from exc
    except RadarrError as exc:
        raise AddFailed(str(exc)) from exc

    activity_log.record_add(
        session,
        item_type=ItemType.MOVIE.value,
        tmdb_id=added.tmdb_id,
        title=added.title,
        instance_id=instance.id,
        user=user,
        trigger_source=trigger_source,
    )

    if user is not None:
        instance_service.remember_choice(session, user, instance.id)

    # The instance now holds this film; reflecting that immediately keeps it out of the gap list
    # without waiting for the next refresh.
    instance_service.refresh_instance_cache(session, instance)

    return AddResult(
        tmdb_id=added.tmdb_id,
        title=added.title,
        instance_id=instance.id,
        instance_name=instance.name,
        searched=search_on_add,
    )


def add_series(
    session: Session,
    *,
    instance: SonarrInstance,
    tmdb_id: int,
    user: User | None = None,
    quality_profile_id: int | None = None,
    root_folder_path: str | None = None,
    monitor_mode: str | None = None,
    search_on_add: bool = True,
    trigger_source: str = TriggerSource.MANUAL.value,
) -> AddResult:
    """Add one show, then record it.

    The monitor mode falls back to the instance's remembered default, and the chosen one becomes
    the next default -- the plan asks for it to be "remembered as the next default" rather than
    asked cold every time.
    """
    profile_id = quality_profile_id or instance.default_quality_profile_id
    root_folder = root_folder_path or instance.default_root_folder
    mode = monitor_mode or instance.default_monitor_mode or MonitorMode.ALL.value

    if not profile_id:
        raise AddFailed(f"No quality profile chosen, and {instance.name} has no default set.")
    if not root_folder:
        raise AddFailed(f"No root folder chosen, and {instance.name} has no default set.")

    client = sonarr_instance_service.client_for(instance)
    try:
        added = client.add_series(
            tmdb_id,
            quality_profile_id=profile_id,
            root_folder_path=root_folder,
            monitor_mode=mode,
            search_on_add=search_on_add,
        )
    except SeriesAlreadyAddedError as exc:
        raise AddFailed(str(exc)) from exc
    except SonarrError as exc:
        raise AddFailed(str(exc)) from exc

    activity_log.record_add(
        session,
        item_type=ItemType.SHOW.value,
        tmdb_id=added.tmdb_id or tmdb_id,
        title=added.title,
        instance_id=instance.id,
        user=user,
        trigger_source=trigger_source,
    )

    if user is not None:
        sonarr_instance_service.remember_choice(session, user, instance.id)
    sonarr_instance_service.remember_monitor_mode(session, instance, mode)
    sonarr_instance_service.refresh_instance_cache(session, instance)

    return AddResult(
        tmdb_id=added.tmdb_id or tmdb_id,
        title=added.title,
        instance_id=instance.id,
        instance_name=instance.name,
        searched=search_on_add,
    )

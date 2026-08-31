"""Config export and import (PROJECT_PLAN.md technical challenge #23).

Covers what a person configured: settings, instances, spin-off mappings, collection excludes and
library selection. Not the activity log, and not the scan cache -- those are local history and
re-derivable data, and shipping them would make the file enormous for no gain.

A restorable export necessarily contains live API keys, so the file is as sensitive as the
credentials in it. Two things follow. The UI must say so plainly rather than presenting it as a
harmless backup, and there is a redacted mode for the far more common case of pasting a config
into a forum thread to ask for help -- which is exactly when someone leaks their keys.

Import validates the whole file before writing anything. A half-applied config is worse than a
rejected one: the user is left with a system in a state neither they nor the file describes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app import __version__
from app.models import (
    CollectionExclude,
    IncludedLibrary,
    RadarrInstance,
    Setting,
    SonarrInstance,
    SpinoffMapping,
)
from app.services.settings_service import SECRET_KEYS

logger = logging.getLogger(__name__)

EXPORT_VERSION = 1

REDACTED = "***REDACTED***"

#: Fields on an instance that hold a credential.
SECRET_FIELDS = frozenset({"api_key"})


class InvalidBackup(ValueError):
    """The file isn't a Franchisarr config export, or is damaged."""


def _instance_dict(instance, *, redact: bool) -> dict:
    return {
        "name": instance.name,
        "url": instance.url,
        "api_key": REDACTED if redact else instance.api_key,
        "default_root_folder": instance.default_root_folder,
        "default_quality_profile_id": instance.default_quality_profile_id,
        "is_default": instance.is_default,
        "hide_if_queued": instance.hide_if_queued,
        **(
            {"default_monitor_mode": instance.default_monitor_mode}
            if isinstance(instance, SonarrInstance)
            else {}
        ),
    }


def export_config(session: Session, *, redact: bool = False) -> dict:
    """Build the backup document.

    `redact` replaces every credential with a placeholder, for sharing. Such a file can't be
    imported to restore working connections, and says so in its own metadata rather than failing
    mysteriously later.
    """
    settings = {}
    for row in session.exec(select(Setting)).all():
        settings[row.key] = REDACTED if (redact and row.key in SECRET_KEYS) else row.value

    return {
        "franchisarr_export_version": EXPORT_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "redacted": redact,
        "settings": settings,
        "radarr_instances": [
            _instance_dict(i, redact=redact) for i in session.exec(select(RadarrInstance)).all()
        ],
        "sonarr_instances": [
            _instance_dict(i, redact=redact) for i in session.exec(select(SonarrInstance)).all()
        ],
        "spinoff_mappings": [
            {
                "source_show_tmdb_id": m.source_show_tmdb_id,
                "spinoff_show_tmdb_id": m.spinoff_show_tmdb_id,
                "source": m.source,
                "confidence": m.confidence,
                "origin_ref": m.origin_ref,
            }
            for m in session.exec(select(SpinoffMapping)).all()
        ],
        "collection_excludes": [
            {"tmdb_collection_id": e.tmdb_collection_id, "tmdb_movie_id": e.tmdb_movie_id}
            for e in session.exec(select(CollectionExclude)).all()
        ],
        "included_libraries": [
            {
                "plex_library_key": lib.plex_library_key,
                "plex_library_name": lib.plex_library_name,
                "library_type": lib.library_type,
                "enabled": lib.enabled,
            }
            for lib in session.exec(select(IncludedLibrary)).all()
        ],
    }


def validate(document: Any) -> dict:
    """Check the shape before anything is written. Raises InvalidBackup with a usable message."""
    if not isinstance(document, dict):
        raise InvalidBackup("That file doesn't contain a Franchisarr config object.")

    version = document.get("franchisarr_export_version")
    if version is None:
        raise InvalidBackup(
            "That doesn't look like a Franchisarr export — it has no version marker."
        )
    if not isinstance(version, int) or version > EXPORT_VERSION:
        raise InvalidBackup(
            f"That export was made by a newer Franchisarr (format {version}); this one "
            f"understands up to {EXPORT_VERSION}. Upgrade before importing it."
        )

    for key, expected in (
        ("settings", dict),
        ("radarr_instances", list),
        ("sonarr_instances", list),
        ("spinoff_mappings", list),
        ("collection_excludes", list),
        ("included_libraries", list),
    ):
        if key in document and not isinstance(document[key], expected):
            raise InvalidBackup(f"The '{key}' section is the wrong shape.")

    for section in ("radarr_instances", "sonarr_instances"):
        for entry in document.get(section, []):
            if not isinstance(entry, dict) or not entry.get("name") or not entry.get("url"):
                raise InvalidBackup(f"An entry in '{section}' is missing its name or URL.")

    return document




def import_config(session: Session, document: Any, *, replace: bool = False) -> dict:
    """Apply a validated backup. Returns a count of what was written.

    Instances whose key is redacted are skipped rather than imported broken -- a connection that
    exists but cannot authenticate is harder to diagnose than one that is plainly absent, and the
    result says how many were skipped and why.

    Importing is additive and idempotent. Restoring a backup onto a system that already holds
    some of the same data is an ordinary thing to do -- re-importing your own export, or merging
    two installs -- and it must not fail on a unique constraint halfway through.
    """
    document = validate(document)
    counts = {"settings": 0, "radarr": 0, "sonarr": 0, "mappings": 0, "excludes": 0,
              "libraries": 0, "skipped_redacted": 0, "already_present": 0}

    from app.services.settings_service import set_setting

    for key, value in (document.get("settings") or {}).items():
        if value == REDACTED:
            counts["skipped_redacted"] += 1
            continue
        set_setting(session, key, value)
        counts["settings"] += 1

    if replace:
        for model in (RadarrInstance, SonarrInstance, SpinoffMapping, CollectionExclude):
            for row in session.exec(select(model)).all():
                session.delete(row)
        # Flush before inserting, so the deletes reach the database first and can't collide with
        # rows about to be re-added -- the same ordering trap the instance caches hit.
        session.flush()

    for section, model, key in (
        ("radarr_instances", RadarrInstance, "radarr"),
        ("sonarr_instances", SonarrInstance, "sonarr"),
    ):
        for entry in document.get(section, []):
            if entry.get("api_key") in (None, "", REDACTED):
                counts["skipped_redacted"] += 1
                continue
            # Same name and URL means the same instance; importing it twice would give the user
            # two identical entries and an ambiguous add dialog.
            if session.exec(
                select(model).where(model.name == entry["name"], model.url == entry["url"])
            ).first():
                counts["already_present"] += 1
                continue
            fields = {k: v for k, v in entry.items() if hasattr(model, k)}
            session.add(model(**fields))
            session.flush()
            counts[key] += 1

    for entry in document.get("spinoff_mappings", []):
        if session.exec(
            select(SpinoffMapping).where(
                SpinoffMapping.source_show_tmdb_id == entry.get("source_show_tmdb_id"),
                SpinoffMapping.spinoff_show_tmdb_id == entry.get("spinoff_show_tmdb_id"),
            )
        ).first():
            counts["already_present"] += 1
            continue
        session.add(SpinoffMapping(**{k: v for k, v in entry.items()
                                      if hasattr(SpinoffMapping, k)}))
        session.flush()
        counts["mappings"] += 1

    for entry in document.get("collection_excludes", []):
        if session.exec(
            select(CollectionExclude).where(
                CollectionExclude.tmdb_collection_id == entry.get("tmdb_collection_id"),
                CollectionExclude.tmdb_movie_id == entry.get("tmdb_movie_id"),
            )
        ).first():
            counts["already_present"] += 1
            continue
        session.add(CollectionExclude(**{k: v for k, v in entry.items()
                                         if hasattr(CollectionExclude, k)}))
        session.flush()
        counts["excludes"] += 1

    for entry in document.get("included_libraries", []):
        existing = session.exec(
            select(IncludedLibrary).where(
                IncludedLibrary.plex_library_key == entry.get("plex_library_key")
            )
        ).first()
        if existing:
            existing.enabled = bool(entry.get("enabled", existing.enabled))
            session.add(existing)
        else:
            session.add(IncludedLibrary(**{k: v for k, v in entry.items()
                                           if hasattr(IncludedLibrary, k)}))
        counts["libraries"] += 1

    session.commit()
    logger.info("Config imported: %s", counts)
    return counts

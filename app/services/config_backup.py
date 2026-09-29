"""Config export and import (docs/DESIGN.md technical challenge #23).

Covers what a person configured: settings, instances, spin-off mappings, collection excludes,
library selection, and each person's dismissals. Not the activity log, and not the scan cache --
those are local history and re-derivable data, and shipping them would make the file enormous
for no gain.

Dismissals are keyed by username rather than user id, because ids are assigned in whatever order
people first signed in and will not match on a new install. A dismissal whose user does not
exist yet is skipped and counted, not attached to whoever ran the import.

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
    DismissedItem,
    IncludedLibrary,
    MediaServer,
    RadarrInstance,
    Setting,
    SeerrInstance,
    SonarrInstance,
    SpinoffMapping,
    User,
)
from app.services.settings_service import SECRET_KEYS

logger = logging.getLogger(__name__)

EXPORT_VERSION = 1

REDACTED = "***REDACTED***"

#: Fields on an instance that hold a credential.
SECRET_FIELDS = frozenset({"api_key", "credential"})

#: Setting keys exports before 0.13 used for the single media server. They are translated into a
#: media_servers entry on import rather than written back as settings nothing reads.
LEGACY_SERVER_KEYS = ("media_server", "plex_url", "plex_token", "jellyfin_url", "jellyfin_api_key",
                      "emby_url", "emby_api_key", "plex_machine_identifier")


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
        "media_servers": [
            {
                "name": s.name,
                "kind": s.kind,
                "url": s.url,
                "credential": REDACTED if redact else s.credential,
                "enabled": s.enabled,
                "watched_user": s.watched_user,
            }
            for s in session.exec(select(MediaServer)).all()
        ],
        "radarr_instances": [
            _instance_dict(i, redact=redact) for i in session.exec(select(RadarrInstance)).all()
        ],
        "sonarr_instances": [
            _instance_dict(i, redact=redact) for i in session.exec(select(SonarrInstance)).all()
        ],
        "seerr_instances": [
            {"name": i.name, "kind": i.kind, "url": i.url,
             "api_key": REDACTED if redact else i.api_key, "is_default": i.is_default}
            for i in session.exec(select(SeerrInstance)).all()
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
                "server": _server_name(session, lib.server_id),
                "library_key": lib.library_key,
                "library_name": lib.library_name,
                "library_type": lib.library_type,
                "enabled": lib.enabled,
            }
            for lib in session.exec(select(IncludedLibrary)).all()
        ],
        "dismissed_items": [
            {
                "username": _username(session, d.user_id),
                "item_type": d.item_type,
                "tmdb_id": d.tmdb_id,
            }
            for d in session.exec(select(DismissedItem)).all()
            if _username(session, d.user_id)
        ],
    }


def _username(session: Session, user_id: int) -> str | None:
    user = session.get(User, user_id)
    if user is None:
        return None
    return user.external_username or user.local_username


def _user_by_name(session: Session, name: str) -> User | None:
    return session.exec(
        select(User).where((User.external_username == name) | (User.local_username == name))
    ).first()


def validate(document: Any) -> dict:
    """Check the shape before anything is written. Raises InvalidBackup with a usable message."""
    if not isinstance(document, dict):
        raise InvalidBackup("That file doesn't contain a Franchisarr config object.")

    version = document.get("franchisarr_export_version")
    if version is None:
        raise InvalidBackup(
            "That doesn't look like a Franchisarr export — it has no version marker."
        )
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise InvalidBackup("That export's version marker is damaged.")
    if version > EXPORT_VERSION:
        raise InvalidBackup(
            f"That export was made by a newer Franchisarr (format {version}); this one "
            f"understands up to {EXPORT_VERSION}. Upgrade before importing it."
        )

    for key, expected in (
        ("settings", dict),
        ("media_servers", list),
        ("radarr_instances", list),
        ("sonarr_instances", list),
        ("seerr_instances", list),
        ("spinoff_mappings", list),
        ("collection_excludes", list),
        ("included_libraries", list),
        ("dismissed_items", list),
    ):
        if key in document and not isinstance(document[key], expected):
            raise InvalidBackup(f"The '{key}' section is the wrong shape.")

    for section in ("media_servers", "radarr_instances", "sonarr_instances", "seerr_instances",
                    "spinoff_mappings", "collection_excludes", "included_libraries",
                    "dismissed_items"):
        for entry in document.get(section, []):
            if not isinstance(entry, dict):
                raise InvalidBackup(f"An entry in '{section}' is the wrong shape.")

    for section in ("media_servers", "radarr_instances", "sonarr_instances", "seerr_instances"):
        for entry in document.get(section, []):
            if not isinstance(entry.get("name"), str) or not entry["name"].strip() \
                    or not _is_http_url(entry.get("url")):
                raise InvalidBackup(f"An entry in '{section}' is missing its name or a valid URL.")

    return document


def _server_name(session: Session, server_id: int) -> str | None:
    server = session.get(MediaServer, server_id)
    return server.name if server else None


def _legacy_server(settings: dict) -> dict | None:
    """The media server a pre-0.13 export described in its settings, as a media_servers entry."""
    kind = (settings.get("media_server") or "").strip().lower()
    if kind not in ("plex", "jellyfin", "emby"):
        kind = next((k for k in ("plex", "jellyfin", "emby") if settings.get(f"{k}_url")), None)
    if kind is None:
        return None
    credential = settings.get("plex_token" if kind == "plex" else f"{kind}_api_key")
    url = settings.get(f"{kind}_url")
    if not (url and credential):
        return None
    return {"name": kind.capitalize(), "kind": kind, "url": url, "credential": credential,
            "enabled": True, "machine_identifier": settings.get("plex_machine_identifier")}




def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    from urllib.parse import urlsplit

    parts = urlsplit(value.strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


# What each section may set: exactly the fields export_config writes, with their types. Anything
# else in a file is ignored -- in particular a row's `id`, and a server's `machine_identifier`,
# which decides whose Plex account administers the install. A backup is data about *your* setup;
# it has no business choosing primary keys or identities.
_STR, _INT, _BOOL = (str,), (int,), (bool,)
_SERVER_FIELDS = {"name": _STR, "kind": _STR, "url": _STR, "credential": _STR,
                  "enabled": _BOOL, "watched_user": _STR}
_INSTANCE_FIELDS = {"name": _STR, "url": _STR, "api_key": _STR, "default_root_folder": _STR,
                    "default_quality_profile_id": _INT, "is_default": _BOOL,
                    "hide_if_queued": _BOOL, "default_monitor_mode": _STR}
_SEERR_FIELDS = {"name": _STR, "kind": _STR, "url": _STR, "api_key": _STR, "is_default": _BOOL}
_MAPPING_FIELDS = {"source_show_tmdb_id": _INT, "spinoff_show_tmdb_id": _INT, "source": _STR,
                   "confidence": _STR, "origin_ref": _STR}
_EXCLUDE_FIELDS = {"tmdb_collection_id": _INT, "tmdb_movie_id": _INT}
_LIBRARY_FIELDS = {"library_key": _STR, "library_name": _STR, "library_type": _STR,
                   "enabled": _BOOL}


def _pick(entry: dict, allowed: dict[str, tuple[type, ...]], model) -> dict:  # noqa: ANN001
    """The allowed fields of `entry` that have the right type and exist on `model`. A bool is
    not accepted where an int is expected, even though Python says True is an int."""
    picked = {}
    for key, types in allowed.items():
        if key not in entry or entry[key] is None or not hasattr(model, key):
            continue
        value = entry[key]
        if isinstance(value, bool) and bool not in types:
            continue
        if isinstance(value, types):
            picked[key] = value
    return picked


def _importable_settings() -> set[str]:
    """Settings a backup may restore: every SettingKey except values this install generates for
    itself. The Plex client id is one: it's what plex.tv ties this install's sign-in PINs to.
    Lists of this install's server ids are others: imported servers get new ids."""
    from app.services.settings_service import SettingKey

    keys = {v for k, v in vars(SettingKey).items() if k.isupper() and isinstance(v, str)}
    return keys - {SettingKey.PLEX_CLIENT_ID, SettingKey.SOLO_RESTORE,
                   SettingKey.PLAYLIST_SYNC_TARGETS, SettingKey.FRANCHISARR_PLAYLIST_SERVERS,
                   SettingKey.FRANCHISARR_PLAYLISTS_TO_ADOPT}


def _setting_value_ok(key: str, value: str) -> bool:
    from app.models import WebhookFormat
    from app.services.settings_service import SettingKey

    if key == SettingKey.WEBHOOK_FORMAT:
        return value in {f.value for f in WebhookFormat}
    if key in (SettingKey.SCAN_SCHEDULE_CRON, SettingKey.PLAYLIST_SYNC_CRON):
        from app.services.scheduler import InvalidSchedule, validate_cron

        try:
            validate_cron(value)
        except InvalidSchedule:
            return False
        return True
    if key == SettingKey.UPDATE_RELEASES_URL:
        return value == "" or value.startswith("https://")
    return len(value) <= 10_000


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
    counts = {"settings": 0, "radarr": 0, "sonarr": 0, "seerr": 0, "mappings": 0, "excludes": 0,
              "dismissals": 0, "dismissals_unmatched": 0,
              "libraries": 0, "skipped_redacted": 0, "already_present": 0, "media_servers": 0,
              "skipped_invalid": 0}

    from app.services.settings_service import set_setting

    settings = dict(document.get("settings") or {})
    servers = list(document.get("media_servers") or [])
    legacy = _legacy_server(settings)
    if legacy and not servers:
        servers.append(legacy)
    for key in LEGACY_SERVER_KEYS:
        if settings.pop(key, None) == REDACTED:
            counts["skipped_redacted"] += 1

    allowed_settings = _importable_settings()
    for key, value in settings.items():
        if value == REDACTED:
            counts["skipped_redacted"] += 1
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, (int, float)):
            value = str(value)
        if key not in allowed_settings or not isinstance(value, str) \
                or not _setting_value_ok(key, value):
            counts["skipped_invalid"] += 1
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

    for entry in servers:
        if entry.get("credential") in (None, "", REDACTED):
            counts["skipped_redacted"] += 1
            continue
        if session.exec(
            select(MediaServer).where(MediaServer.name == entry["name"])
        ).first() or session.exec(
            select(MediaServer).where(MediaServer.url == entry["url"], MediaServer.kind == entry.get("kind"))
        ).first():
            counts["already_present"] += 1
            continue
        fields = _pick(entry, _SERVER_FIELDS, MediaServer)
        if fields.get("kind") not in ("plex", "jellyfin", "emby") or not _is_http_url(fields.get("url")):
            counts["skipped_invalid"] += 1
            continue
        # Always switched off. A media server decides who can sign in -- its owner or its admins
        # administer this install -- so a file must never be able to hand that to someone. The
        # admin reviews each imported server on the Servers page and switches it on.
        fields["enabled"] = False
        session.add(MediaServer(**fields))
        session.flush()
        counts["media_servers"] += 1

    for section, model, key in (
        ("radarr_instances", RadarrInstance, "radarr"),
        ("sonarr_instances", SonarrInstance, "sonarr"),
        ("seerr_instances", SeerrInstance, "seerr"),
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
            allowed = _SEERR_FIELDS if model is SeerrInstance else _INSTANCE_FIELDS
            fields = _pick(entry, allowed, model)
            if not _is_http_url(fields.get("url")) or not fields.get("api_key"):
                counts["skipped_invalid"] += 1
                continue
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
        fields = _pick(entry, _MAPPING_FIELDS, SpinoffMapping)
        if "source_show_tmdb_id" not in fields or "spinoff_show_tmdb_id" not in fields:
            counts["skipped_invalid"] += 1
            continue
        session.add(SpinoffMapping(**fields))
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
        fields = _pick(entry, _EXCLUDE_FIELDS, CollectionExclude)
        if len(fields) != 2:
            counts["skipped_invalid"] += 1
            continue
        session.add(CollectionExclude(**fields))
        session.flush()
        counts["excludes"] += 1

    for entry in document.get("dismissed_items", []):
        if not isinstance(entry, dict) or not entry.get("username"):
            continue
        user = _user_by_name(session, str(entry["username"]))
        if user is None:
            counts["dismissals_unmatched"] += 1
            continue
        try:
            tmdb_id = int(entry.get("tmdb_id"))
        except (TypeError, ValueError):
            continue
        item_type = str(entry.get("item_type") or "")
        if session.exec(
            select(DismissedItem).where(
                DismissedItem.user_id == user.id,
                DismissedItem.item_type == item_type,
                DismissedItem.tmdb_id == tmdb_id,
            )
        ).first():
            counts["already_present"] += 1
            continue
        session.add(DismissedItem(user_id=user.id, item_type=item_type, tmdb_id=tmdb_id))
        session.flush()
        counts["dismissals"] += 1

    all_servers = session.exec(select(MediaServer)).all()
    for entry in document.get("included_libraries", []):
        # Exports from before 0.12 used Plex's names for these fields; before 0.13 they named no
        # server, which is fine when there is only one to choose from.
        entry = {
            **entry,
            "library_key": entry.get("library_key") or entry.get("plex_library_key"),
            "library_name": entry.get("library_name") or entry.get("plex_library_name"),
        }
        server = next((s for s in all_servers if s.name == entry.get("server")), None)
        if server is None and len(all_servers) == 1:
            server = all_servers[0]
        if server is None:
            counts["skipped_unmatched"] = counts.get("skipped_unmatched", 0) + 1
            continue
        existing = session.exec(
            select(IncludedLibrary).where(
                IncludedLibrary.server_id == server.id,
                IncludedLibrary.library_key == entry.get("library_key"),
            )
        ).first()
        if existing:
            if isinstance(entry.get("enabled"), bool):
                existing.enabled = entry["enabled"]
            session.add(existing)
        else:
            fields = _pick(entry, _LIBRARY_FIELDS, IncludedLibrary)
            if not fields.get("library_key"):
                counts["skipped_invalid"] += 1
                continue
            session.add(IncludedLibrary(server_id=server.id, **fields))
        counts["libraries"] += 1

    session.commit()
    logger.info("Config imported: %s", counts)
    return counts
